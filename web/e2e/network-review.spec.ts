import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

const headers = ['record_id','npi','provider_name','address','city','state','zip','phone','location_id','network_code','organization_code','participation_status','effective_date','end_date'];
const row = (record_id:string, network_code:string, location_id:string, changes:Record<string,string> = {}) => ({
  record_id,npi:'1000000001',provider_name:'Synthetic Provider',address:'10 Fiction St',city:'Example',state:'TN',zip:'01234',phone:'5550100000',location_id,network_code,organization_code:'CLINIC',participation_status:'listed',effective_date:'2026-01-01',end_date:'',...changes,
});
const csv = (rows:ReturnType<typeof row>[]) => `${headers.join(',')}\n${rows.map((item) => headers.map((header) => item[header as keyof typeof item] ?? '').join(',')).join('\n')}${rows.length ? '\n' : ''}`;
const body = async (response:import('@playwright/test').APIResponse) => {expect(response.ok(),await response.text()).toBeTruthy();return response.json();};
async function setup(page:Page,source:string) {
  const post = (path:string,payload:Record<string,unknown>) => page.request.post(`/api${path}`,{data:{...payload,actor:'Synthetic Reviewer',reason:'Reviewed synthetic fixture'}});
  const payer = await body(await post('/catalog/organizations',{label:`Synthetic Payer ${source}`,kind:'payer'}));
  const clinic = await body(await post('/catalog/organizations',{label:`Synthetic Clinic ${source}`,kind:'clinic'}));
  const cedar = await body(await post('/catalog/networks',{label:`CEDAR ${source}`,payer_organization_id:payer.id}));
  const pine = await body(await post('/catalog/networks',{label:`PINE ${source}`,payer_organization_id:payer.id}));
  const north = await body(await post('/catalog/locations',{label:`NORTH ${source}`,organization_id:clinic.id}));
  const south = await body(await post('/catalog/locations',{label:`SOUTH ${source}`,organization_id:clinic.id}));
  const bindings = {network:{} as Record<string,string>,location:{} as Record<string,string>,organization:{} as Record<string,string>};
  for (const [kind,code,target_id] of [
    ['network','CEDAR',cedar.id],['network','PINE',pine.id],['location','NORTH',north.id],['location','SOUTH',south.id],['organization','CLINIC',clinic.id],
  ]) {
    const result = await body(await post('/catalog/bindings',{source,kind,source_key:code,target_id}));
    bindings[kind as keyof typeof bindings][code] = result.id;
  }
  return {cedar,pine,north,south,bindings};
}
async function receive(page:Page,source:string,scope:string,name:string,content:string,completeness='bounded') {
  const params = new URLSearchParams({filename:name,source,designation:'synthetic',profile:'flat',dataset_scope:scope,completeness});
  return body(await page.request.post(`/api/intakes/files?${params}`,{data:Buffer.from(content),headers:{'Content-Type':'application/octet-stream'}}));
}
async function uploadUI(page:Page,name:string,content:string) {
  await page.getByLabel('Source file',{exact:true}).setInputFiles({name,mimeType:'text/csv',buffer:Buffer.from(content)});
  await page.getByRole('button',{name:'Upload and preview'}).click();
  await expect(page.getByRole('heading',{name})).toBeVisible();
}
async function workbook(path:string) {
  const script = `import json,sys,io\nfrom openpyxl import load_workbook\nw=load_workbook(io.BytesIO(open(sys.argv[1],'rb').read()),read_only=True,data_only=False)\ndef rows(name):return list(w[name].values)[1:] if name in w.sheetnames else []\nprint(json.dumps({'sheets':w.sheetnames,'case_ids':[r[0] for r in rows('Cases')],'participation_count':len(rows('Participations')),'catalog_network_ids':[r[1] for r in rows('Catalog') if r[0]=='networks'],'review_count':len(rows('Review evidence'))}))\nw.close()`;
  return JSON.parse(execFileSync('python3',['-c',script,path],{encoding:'utf8'}));
}

test('changed network delivery creates review work and scoped handoffs without changing human state', async ({page},info) => {
  test.setTimeout(120_000);
  const source = `n3-source-${info.project.name}`;
  const scope = `n3-scope-${info.project.name}`;
  const {cedar,pine,bindings} = await setup(page,source);
  const baseline = await receive(page,source,scope,'baseline-network.csv',csv([row('LIST-A','CEDAR','NORTH'),row('LIST-B','CEDAR','SOUTH'),row('LIST-C','PINE','NORTH')]));
  const mapped = await body(await page.request.post(`/api/intakes/${baseline.id}/mapping`,{data:{mapping:Object.fromEntries(headers.map((name) => [name,name])),roster_kind:'network',bindings}}));
  expect(mapped.preview.valid_count).toBe(3);
  const revision = await body(await page.request.post(`/api/intakes/${baseline.id}/saved-mappings`,{data:{name:'Reviewed network columns',actor:'Synthetic Reviewer',reason:'Exact source codes and required columns',expected_attempt:mapped.attempt_id}}));
  const pinned = await body(await page.request.post(`/api/intakes/${baseline.id}/mapping`,{data:{mapping_revision_id:revision.id}}));
  await body(await page.request.post(`/api/intakes/${baseline.id}/commit`,{data:{policy:'valid_rows',actor:'Synthetic Reviewer',reason:'Baseline accepted',expected_attempt:pinned.attempt_id}}));

  await page.goto('/?view=intake');
  await page.getByLabel('Source namespace',{exact:true}).fill(source);
  await page.getByText('Delivery scope and source date (optional)').click();
  await page.getByLabel('Dataset scope').fill(scope);
  const changed = csv([row('LIST-A','CEDAR','NORTH',{phone:'5550100008'}),row('LIST-B','CEDAR','SOUTH',{effective_date:'bad-date'}),row('UNKNOWN','UNKNOWN','NORTH')]);
  await uploadUI(page,'changed-network.csv',changed);
  await page.getByRole('combobox',{name:'Saved mapping revision'}).selectOption(revision.id);
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('1 valid · 2 quarantined · 3 total')).toBeVisible();
  await page.getByText('Comparison with prior source deliveries').click();
  await expect(page.locator('.ri-counts')).toContainText('changed: 1');
  await expect(page.locator('.ri-counts')).toContainText('blocked invalid: 1');
  await expect(page.locator('.ri-counts')).toContainText('missing: 1');
  await page.getByRole('combobox',{name:'Filter changes'}).selectOption('changed');
  await page.locator('.ri-entries summary').first().click();
  await expect(page.getByRole('cell',{name:'5550100000'})).toBeVisible();
  await expect(page.getByRole('cell',{name:'5550100008'})).toBeVisible();
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Accept changed row; preserve invalid and missing review');
  await page.getByRole('button',{name:'Accept valid rows'}).click();
  await expect(page.getByRole('heading',{name:'Linked cases'})).toBeVisible();

  await page.goto('/?view=work');
  const networkFilter = page.getByRole('combobox',{name:'Network filter'});
  await networkFilter.selectOption(cedar.id);
  await expect(networkFilter).toHaveValue(cedar.id);
  await expect(page.locator('.iw-list li button')).toHaveCount(3);
  await expect(page.getByRole('link',{name:'Download selected network XLSX'})).toHaveAttribute('href',`/api/work-export.xlsx?network_id=${cedar.id}`);
  expect(new URL(page.url()).searchParams.get('network_id')).toBe(cedar.id);
  await page.reload();
  await expect(page.getByRole('combobox',{name:'Network filter'})).toHaveValue(cedar.id);
  await page.getByRole('button',{name:/Quarantined participation requires review/}).click();
  await expect(page.getByRole('heading',{name:'Network participation scope'})).toBeVisible();
  await expect(page.getByText(/Source-listed status and dates are source assertions/)).toBeVisible();
  await expect(page.locator('.nw-review').getByText(/effective_date must use YYYY-MM-DD/)).toBeVisible();
  await page.getByRole('combobox',{name:'Action',exact:true}).selectOption('assign');
  await page.getByLabel('actor *').fill('Synthetic Reviewer');
  await page.getByLabel('reason *').fill('Follow up invalid source date');
  await page.getByLabel('owner *').fill('Clinic coordinator');
  await page.getByRole('button',{name:'Save review event'}).click();
  await expect(page.getByText(/Current owner: Clinic coordinator/)).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath('network-work-scope.png'),fullPage:true});

  const caseJsonPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download case JSON'}).click();
  const caseJsonDownload = await caseJsonPromise;
  const caseJson = JSON.parse(await readFile((await caseJsonDownload.path())!,'utf8'));
  expect(caseJson.cases).toHaveLength(1);
  expect(caseJson.cases[0].network_id ?? caseJson.cases[0].scope?.network_id).toBe(cedar.id);
  expect(caseJson.review_evidence.some((item:{status:string}) => item.status === 'blocked_invalid')).toBeTruthy();
  const networkJsonPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download selected network JSON'}).click();
  const networkJsonDownload = await networkJsonPromise;
  const networkJson = JSON.parse(await readFile((await networkJsonDownload.path())!,'utf8'));
  expect(networkJson.network_id).toBe(cedar.id);
  expect(networkJson.cases).toHaveLength(3);
  expect(networkJson.cases.every((item:{scope:{network_id:string}}) => item.scope.network_id === cedar.id)).toBeTruthy();
  expect(networkJson.participations.every((item:{network_id:string}) => item.network_id === cedar.id)).toBeTruthy();
  expect(networkJson.catalog.networks.every((item:{id:string}) => item.id !== pine.id)).toBeTruthy();
  const networkXlsxPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download selected network XLSX'}).click();
  const networkXlsx = await workbook((await (await networkXlsxPromise).path())!);
  expect(networkXlsx.case_ids).toHaveLength(3);
  expect(networkXlsx.catalog_network_ids).not.toContain(pine.id);
  expect(networkXlsx.review_count).toBeGreaterThanOrEqual(1);
  const caseXlsxPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download case XLSX'}).click();
  const caseXlsx = await workbook((await (await caseXlsxPromise).path())!);
  expect(caseXlsx.case_ids).toHaveLength(1);
  expect(caseXlsx.catalog_network_ids).not.toContain(pine.id);

  await page.goto('/?view=intake');
  await page.getByLabel('Source namespace',{exact:true}).fill(source);
  await page.getByText('Delivery scope and source date (optional)').click();
  await page.getByLabel('Dataset scope').fill(scope);
  await page.getByRole('combobox',{name:'Completeness'}).selectOption('full');
  await uploadUI(page,'empty-full-network.csv',csv([]));
  await page.getByRole('combobox',{name:'Saved mapping revision'}).selectOption(revision.id);
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('0 valid · 0 quarantined · 0 total')).toBeVisible();
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Full empty source snapshot reviewed');
  await page.getByRole('button',{name:'Accept empty snapshot as absence evidence'}).click();
  await expect(page.getByRole('heading',{name:'Linked cases'})).toBeVisible();
});
