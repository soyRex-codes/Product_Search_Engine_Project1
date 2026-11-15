"""Independently compare prepared files with the pinned source data."""
import json
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
c = duckdb.connect()
for name, path in [('e','data/raw/shopping_queries_dataset_examples.parquet'), ('p','data/raw/shopping_queries_dataset_products.parquet'), ('development','data/prepared/development.parquet'), ('evaluation','data/prepared/evaluation.parquet')]:
    c.read_parquet(str(ROOT / path)).create_view(name)
c.read_csv(str(ROOT / 'data/raw/shopping_queries_dataset_sources.csv')).create_view('s')
queries = {
    'missing_example_keys': 'SELECT count(*) FROM e WHERE example_id IS NULL OR query_id IS NULL OR product_id IS NULL OR product_locale IS NULL',
    'missing_product_keys': 'SELECT count(*) FROM p WHERE product_id IS NULL OR product_locale IS NULL',
    'invalid_splits': "SELECT count(*) FROM e WHERE split IS NULL OR split NOT IN ('train','test')",
    'missing_sources': 'SELECT count(*) FROM e ANTI JOIN s USING(query_id)',
    'empty_sources': "SELECT count(*) FROM s WHERE source IS NULL OR trim(source)='' OR query_id IS NULL",
}
results = {name: c.execute(sql).fetchone()[0] for name,sql in queries.items()}
for name,split,count in [('development','train',250),('evaluation','test',1000)]:
    c.execute(f"CREATE OR REPLACE TEMP VIEW expected AS WITH ids AS (SELECT query_id FROM e WHERE product_locale='us' AND small_version AND split='{split}' GROUP BY 1 ORDER BY md5('42:' || cast(query_id AS VARCHAR)),query_id LIMIT {count}) SELECT e.*,p.product_title,p.product_bullet_point,p.product_description,p.product_brand,p.product_color,coalesce(p.product_title,'') || ' ' || left(coalesce(p.product_bullet_point,''),1000) AS product_text FROM e JOIN ids USING(query_id) LEFT JOIN p USING(product_id,product_locale) WHERE e.product_locale='us' AND e.small_version AND e.split='{split}'").fetchall()
    for suffix,left,right in [('missing_or_changed_rows','expected',name),('extra_or_changed_rows',name,'expected')]:
        results[f'{name}_{suffix}'] = c.execute(f'SELECT count(*) FROM (SELECT * FROM {left} EXCEPT ALL SELECT * FROM {right})').fetchone()[0]
results['prepared_query_overlap'] = c.execute('SELECT count(*) FROM (SELECT DISTINCT query_id FROM development INTERSECT SELECT DISTINCT query_id FROM evaluation)').fetchone()[0]
(ROOT / 'reports/prepush_verification.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
if any(results.values()):
    raise SystemExit('FAIL: data inconsistencies found')
print('PASS: independent exported-data verification')
