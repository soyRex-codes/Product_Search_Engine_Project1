"""Audit full ESCI files, export proposal samples, and smoke-test text scoring.

Run from any directory. Only development queries are used for the scoring check.
"""
import json
import math
import platform
import re
import statistics
import time
from collections import Counter
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]

def main():
    started = time.perf_counter()
    con = duckdb.connect()
    con.execute("SET memory_limit='2GB'")
    con.execute('SET threads=4')
    for table, filename in [('examples', 'examples'), ('products', 'products')]:
        path = ROOT / f'data/raw/shopping_queries_dataset_{filename}.parquet'
        con.read_parquet(str(path)).create_view(table)
    def rows(sql):
        result = con.execute(sql)
        names = [d[0] for d in result.description]
        return [dict(zip(names, row)) for row in result.fetchall()]
    def scalar(sql):
        return con.execute(sql).fetchone()[0]
    report = {'environment': {'python': platform.python_version(), 'duckdb': duckdb.__version__, 'platform': platform.platform()}, 'source': json.loads((ROOT / 'data/raw/manifest.json').read_text())}
    report['schemas'] = {table: rows(f'DESCRIBE {table}') for table in ['examples', 'products']}
    con.read_csv(str(ROOT / 'data/raw/shopping_queries_dataset_sources.csv')).create_view('sources')
    report['sources'] = rows('SELECT count(*) AS rows, count(DISTINCT query_id) AS queries FROM sources')[0]
    report['counts'] = {table: scalar(f'SELECT count(*) FROM {table}') for table in ['examples', 'products']}
    report['locales'] = rows('SELECT product_locale, count(*) AS judgments FROM examples GROUP BY 1 ORDER BY 1')
    con.execute("CREATE TABLE task1 AS SELECT * FROM examples WHERE small_version=true AND product_locale='us'")
    report['task1_us_splits'] = rows('SELECT split, count(*) AS judgments, count(DISTINCT query_id) AS queries FROM task1 GROUP BY 1 ORDER BY 1')
    report['labels'] = rows('SELECT split, esci_label, count(*) AS judgments FROM task1 GROUP BY 1,2 ORDER BY 1,2')
    checks = {}
    checks['duplicate_product_keys'] = scalar('SELECT count(*) FROM (SELECT product_id, product_locale FROM products GROUP BY 1,2 HAVING count(*)>1)')
    checks['duplicate_example_ids'] = scalar('SELECT count(*)-count(DISTINCT example_id) FROM examples')
    checks['duplicate_task1_pairs'] = scalar('SELECT count(*) FROM (SELECT query_id,product_id,product_locale FROM task1 GROUP BY 1,2,3 HAVING count(*)>1)')
    checks['invalid_labels'] = scalar("SELECT count(*) FROM examples WHERE esci_label IS NULL OR esci_label NOT IN ('E','S','C','I')")
    checks['missing_task1_keys_or_query'] = scalar("SELECT count(*) FROM task1 WHERE query_id IS NULL OR product_id IS NULL OR query IS NULL OR trim(query)=''")
    checks['query_ids_across_splits'] = scalar('SELECT count(*) FROM (SELECT query_id FROM task1 GROUP BY 1 HAVING count(DISTINCT split)>1)')
    checks['query_texts_across_splits'] = scalar("SELECT count(*) FROM (SELECT lower(trim(query)) FROM task1 GROUP BY 1 HAVING count(DISTINCT split)>1)")
    checks['inconsistent_query_text'] = scalar('SELECT count(*) FROM (SELECT query_id FROM task1 GROUP BY 1 HAVING count(DISTINCT query)>1)')
    checks['unmatched_products_all_examples'] = scalar('SELECT count(*) FROM examples e ANTI JOIN products p USING(product_id, product_locale)')
    con.execute('CREATE TABLE joined AS SELECT e.*, p.product_title,p.product_bullet_point,p.product_description,p.product_brand,p.product_color FROM task1 e LEFT JOIN products p USING(product_id,product_locale)')
    checks['join_row_count_difference'] = scalar('SELECT (SELECT count(*) FROM joined)-(SELECT count(*) FROM task1)')
    report['checks'] = checks
    report['pools_over_40'] = rows('SELECT split,count(*) AS queries,max(n) AS max_candidates FROM (SELECT split,query_id,count(*) AS n FROM task1 GROUP BY 1,2) WHERE n>40 GROUP BY 1 ORDER BY 1')
    report['largest_pools'] = rows('SELECT split,query_id, min(query) AS query,count(*) AS candidates FROM task1 GROUP BY 1,2 ORDER BY candidates DESC LIMIT 5')
    report['missing_text'] = {}
    for field in ['product_title','product_bullet_point','product_description','product_brand','product_color']:
        report['missing_text'][field] = scalar(f"SELECT count(*) FROM joined WHERE {field} IS NULL OR trim({field})=''")
    report['candidate_pools'] = rows('SELECT split,min(n) AS min_candidates,max(n) AS max_candidates,avg(n) AS mean_candidates,sum(CASE WHEN exacts=0 THEN 1 ELSE 0 END) AS queries_without_exact,sum(CASE WHEN positives=0 THEN 1 ELSE 0 END) AS queries_without_positive FROM (SELECT split,query_id,count(*) AS n,count(*) FILTER(WHERE esci_label=\'E\') AS exacts,count(*) FILTER(WHERE esci_label<>\'I\') AS positives FROM task1 GROUP BY 1,2) GROUP BY 1 ORDER BY 1')
    con.execute("CREATE TABLE prepared AS SELECT *, coalesce(product_title,'') || ' ' || left(coalesce(product_bullet_point,''),1000) AS product_text FROM joined")
    exports = {}
    for name, split, count in [('development','train',250),('evaluation','test',1000)]:
        # MD5 provides a stable, version-independent seeded ordering of query IDs.
        con.execute(f"CREATE TEMP TABLE selected_{name} AS SELECT query_id FROM task1 WHERE split='{split}' GROUP BY 1 ORDER BY md5('42:' || cast(query_id AS VARCHAR)),query_id LIMIT {count}")
        query = f'SELECT p.* FROM prepared p JOIN selected_{name} s USING(query_id) ORDER BY query_id,product_id'
        path = ROOT / f'data/prepared/{name}.parquet'
        path.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f'COPY ({query}) TO ? (FORMAT PARQUET)', [str(path)])
        exports[name] = rows(f'SELECT count(*) AS judgments,count(DISTINCT query_id) AS queries FROM ({query})')[0]
    report['samples'] = {'seed': 42, 'selection': "order query IDs by md5('42:' + query_id)", 'bullet_character_limit':1000, **exports}
    # A simple BM25 over each supplied pool exercises text, IDs, labels, sorting, and nDCG.
    samples = rows('SELECT query_id,query,product_id,product_text,esci_label FROM prepared JOIN selected_development USING(query_id) ORDER BY query_id,product_id')
    groups = {}
    for row in samples:
        groups.setdefault(row['query_id'],[]).append(row)
    tokenize = lambda text: re.findall(r'[a-z0-9]+', text.lower())
    gains = {'E':1.,'S':.1,'C':.01,'I':0.}
    ndcgs, latencies = [], []
    for group in groups.values():
        docs = [Counter(tokenize(r['product_text'])) for r in group]
        lens = [sum(d.values()) for d in docs]
        avg = statistics.mean(lens) or 1
        df = Counter(term for doc in docs for term in doc)
        terms = set(tokenize(group[0]['query']))
        tick = time.perf_counter()
        scores = [sum(math.log(1+(len(docs)-df[t]+.5)/(df[t]+.5))*doc[t]*2.5/(doc[t]+1.5*(.25+.75*length/avg)) for t in terms if doc[t]) for doc,length in zip(docs,lens)]
        # Stable product-ID tie break; labels and source row order never enter scoring.
        order = sorted(range(len(group)),key=lambda i:(-scores[i],group[i]['product_id']))
        latencies.append((time.perf_counter()-tick)*1000)
        dcg = lambda values: sum(v/math.log2(i+2) for i,v in enumerate(values[:10]))
        ideal = dcg(sorted([gains[r['esci_label']] for r in group],reverse=True))
        if ideal: ndcgs.append(dcg([gains[group[i]['esci_label']] for i in order])/ideal)
    report['smoke_test'] = {'method':'BM25 with pool-local document frequencies; development only; not final retrieval benchmark', 'queries':len(groups),'queries_with_positive_gain':len(ndcgs),'mean_ndcg_at_10':statistics.mean(ndcgs),'median_scoring_ms':statistics.median(latencies),'latency_scope':'Only BM25 scoring and sorting; excludes tokenization, indexing, model inference and I/O'}
    report['elapsed_seconds'] = time.perf_counter()-started
    out = ROOT / 'reports/data_validation.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['schemas','source']},indent=2))
    fatal = {k:v for k,v in checks.items() if k!='query_texts_across_splits' and v!=0}
    if fatal: raise SystemExit(f'Validation failures: {fatal}')
    assert exports['development']['queries']==250 and exports['evaluation']['queries']==1000
    assert len(ndcgs)>0 and all(0<=v<=1+1e-10 for v in ndcgs)
    print('PASS: integrity, schema loading, joins, keys, splits, sample sizes and ranking smoke check')

if __name__=='__main__':
    main()
