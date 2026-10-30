import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

type Catalog = {
  organizations:{id:string;label:string}[];
  networks:{id:string;label:string}[];
  locations:{id:string;label:string}[];
  bindings:{id:string;source:string;kind:string;source_key:string;current:boolean}[];
};
const headers = ['record_id','npi','provider_name','address','city','state','zip','phone','location_id','network_code','organization_code','participation_status','effective_date','end_date'];
function row(record_id:string, network_code:string, location_id:string, changes:Record<string,string> = {}) {
  return {record_id,npi:'1000000001',provider_name:'Synthetic Provider',address:'10 Fiction St',city:'Example',state:'TN',zip:'01234',phone:'5550100000',location_id,network_code,organization_code:'CLINIC',participation_status:'listed',effective_date:'2026-01-01',end_date:'',...changes};
}
function roster(rows:ReturnType<typeof row>[]) {
  return `${headers.join(',')}\n${rows.map((record) => headers.map((header) => record[header as keyof typeof record] ?? '').join(',')).join('\n')}\n`;
}
async function catalog(page:Page):Promise<Catalog> {
  const response = await page.request.get('/api/catalog');
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function createdId(page:Page, kind:'organizations'|'networks'|'locations', label:string) {
  await expect.poll(async () => (await catalog(page))[kind].find((item) => item.label === label)?.id).toBeTruthy();
  return (await catalog(page))[kind].find((item) => item.label === label)!.id;
}
async function selectId(page:Page, label:string, id:string) {
  const select = page.getByRole('combobox',{name:label,exact:true});
  await select.selectOption(id,{timeout:10_000});
  await expect(select).toHaveValue(id);
}

test('reviewed CEDAR/PINE and NORTH/SOUTH bindings produce three distinct source assertions', async ({page},info) => {
  test.setTimeout(120_000);
  const source = `synthetic-network-${info.project.name}`;
  const suffix = info.project.name;
  await page.goto('/?view=intake');
  await page.getByLabel('Source namespace',{exact:true}).fill(source);
  await page.getByText('Organization and network setup').click();
  await page.getByLabel('Catalog reviewer').fill('Synthetic Reviewer');
  await page.getByLabel('Catalog reason').fill('Reviewed synthetic codebook');
  await expect(page.getByLabel('Binding source')).toHaveValue(source);

  await page.getByLabel('Organization kind').selectOption('payer');
  await page.getByLabel('Organization label').fill(`Synthetic Payer ${suffix}`);
  await page.getByRole('button',{name:'Create organization'}).click();
  const payerId = await createdId(page,'organizations',`Synthetic Payer ${suffix}`);
  await page.getByLabel('Organization kind').selectOption('clinic');
  await page.getByLabel('Organization label').fill(`Synthetic Clinic ${suffix}`);
  await page.getByRole('button',{name:'Create organization'}).click();
  const clinicId = await createdId(page,'organizations',`Synthetic Clinic ${suffix}`);

  for (const network of ['CEDAR','PINE']) {
    await page.getByLabel('Network label').fill(`${network} ${suffix}`);
    await selectId(page,'Payer organization',payerId);
    await page.getByRole('button',{name:'Create network'}).click();
    await createdId(page,'networks',`${network} ${suffix}`);
  }
  for (const location of ['NORTH','SOUTH']) {
    await page.getByLabel('Location label').fill(`${location} ${suffix}`);
    await selectId(page,'Clinic organization',clinicId);
    await page.getByRole('button',{name:'Create location'}).click();
    await createdId(page,'locations',`${location} ${suffix}`);
  }
  const records = await catalog(page);
  const targets = [
    {kind:'network',code:'CEDAR',id:records.networks.find((item) => item.label === `CEDAR ${suffix}`)!.id},
    {kind:'network',code:'PINE',id:records.networks.find((item) => item.label === `PINE ${suffix}`)!.id},
    {kind:'location',code:'NORTH',id:records.locations.find((item) => item.label === `NORTH ${suffix}`)!.id},
    {kind:'location',code:'SOUTH',id:records.locations.find((item) => item.label === `SOUTH ${suffix}`)!.id},
    {kind:'organization',code:'CLINIC',id:clinicId},
  ];
  for (const target of targets) {
    await page.getByLabel('Binding kind').selectOption(target.kind);
    await page.getByLabel('Exact source code').fill(target.code);
    await selectId(page,'Reviewed target',target.id);
    await page.getByRole('button',{name:'Save reviewed binding'}).click();
    await expect.poll(async () => (await catalog(page)).bindings.filter((item) => item.current && item.source === source && item.kind === target.kind && item.source_key === target.code).length).toBe(1);
    await expect(page.getByLabel('Exact source code')).toHaveValue('');
    await expect(page.getByLabel('Binding kind')).toBeEnabled();
  }
  expect((await catalog(page)).bindings.filter((item) => item.current && item.source === source)).toHaveLength(5);

  const csv = roster([
    row('LIST-A','CEDAR','NORTH'),row('LIST-B','CEDAR','SOUTH'),row('LIST-C','PINE','NORTH'),
    row('LIST-U','UNKNOWN','NORTH'),row('LIST-D','CEDAR','NORTH',{effective_date:'2026-05-01',end_date:'2026-04-01'}),
  ]);
  await page.getByLabel('Source file',{exact:true}).setInputFiles({name:'synthetic-network.csv',mimeType:'text/csv',buffer:Buffer.from(csv)});
  await page.getByRole('button',{name:'Upload and preview'}).click();
  await expect(page.getByRole('heading',{name:'synthetic-network.csv'})).toBeVisible();
  await page.getByText('Column mapping and parsing').click();
  await page.getByLabel('Roster kind').selectOption('network');
  for (const target of targets) {
    const group = page.getByRole('group',{name:`${target.kind} source codes`});
    await group.getByRole('checkbox',{name:new RegExp(`^${target.code} →`)}).check();
  }
  await page.getByRole('button',{name:'Save mapping and reprocess'}).click();
  await expect(page.getByText('3 valid · 2 quarantined · 5 total')).toBeVisible();
  await expect(page.getByText('row:5 · Quarantined',{exact:true})).toBeVisible();
  await expect(page.getByText('row:6 · Quarantined',{exact:true})).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath('network-configured-preview.png'),fullPage:true});

  await page.getByText('Save this validated mapping as a revision').click();
  await page.getByLabel('Revision name').fill('Reviewed network roster v1');
  await page.getByLabel('Mapping reviewer').fill('Synthetic Reviewer');
  await page.getByLabel('Mapping reason').fill('Reviewed network and location source codes');
  await page.getByRole('button',{name:'Save mapping revision (does not accept)'}).click();
  await expect(page.getByLabel('Saved mapping revision')).toContainText('Reviewed network roster v1');
  await page.getByLabel('Saved mapping revision').selectOption({index:1});
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('3 valid · 2 quarantined · 5 total')).toBeVisible();
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Accept three source assertions; quarantine invalid rows');
  await page.getByRole('button',{name:'Accept valid rows'}).click();
  await expect(page.getByRole('heading',{name:'Source observations and relationships'})).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Evidence packet JSON'}).click();
  const download = await downloadPromise;
  const packet = JSON.parse(await readFile((await download.path())!,'utf8'));
  expect(packet.observations).toHaveLength(3);
  expect(packet.linked_cases).toHaveLength(3);
  expect(packet.cases).toHaveLength(3);
  expect(packet.cases.every((item:{kind:string;status:string;field_name:string}) => item.kind === 'qa' && item.status === 'new' && item.field_name === 'participation')).toBeTruthy();
  const assertions = packet.observations.map((item:{normalized:{participation:{network_id:string;location_id:string;listed_status:string}}}) => item.normalized.participation);
  expect(new Set(assertions.map((item:{network_id:string;location_id:string}) => `${item.network_id}/${item.location_id}`)).size).toBe(3);
  expect(assertions.every((item:{listed_status:string}) => item.listed_status === 'listed')).toBeTruthy();
  expect(packet.preview.rows.filter((item:{problems:string[]}) => item.problems.length)).toHaveLength(2);
  expect(packet.preview.rows.some((item:{original:{network_code:string}}) => item.original.network_code === 'UNKNOWN')).toBeTruthy();
  expect(Object.keys(packet.attempts.at(-1).spec.binding_snapshot)).toHaveLength(5);
  expect(packet.attempts.at(-1).spec.mapping_revision_id).toBeTruthy();
  const originalPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download original'}).click();
  const original = await originalPromise;
  expect(await readFile((await original.path())!,'utf8')).toBe(csv);
});
