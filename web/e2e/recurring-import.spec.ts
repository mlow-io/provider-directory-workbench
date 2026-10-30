import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const headers = ['record_id','npi','provider_name','address','city','state','zip','phone','location_id','reference_phone'];
const row = ['ROSTER-A','1234567890','Synthetic Avery Example','1 Example Street','Boston','MA','02108','6175550100','NORTH','6175550199'];
const csv = (columns: string[], values: Record<string,string>) => `${columns.join(',')}\n${columns.map((column) => values[column] ?? '').join(',')}\n`;
const base = Object.fromEntries(headers.map((header,index) => [header,row[index]]));

async function upload(page: import('@playwright/test').Page, filename: string, content: string) {
  await page.getByLabel('Source file', {exact:true}).setInputFiles({name:filename,mimeType:'text/csv',buffer:Buffer.from(content)});
  await page.getByRole('button',{name:'Upload and preview'}).click();
  await expect(page.getByRole('heading',{name:filename,exact:true})).toBeVisible();
}
async function reviewAndAccept(page: import('@playwright/test').Page, reason: string) {
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill(reason);
  await page.getByRole('button',{name:'Accept valid rows'}).click();
}

test('reviewed mapping survives column reorder, stale baseline, and missing required headers', async ({page}, info) => {
  test.setTimeout(90_000);
  const source = `recurring-${info.project.name}`;
  await page.goto('/?view=intake');
  await page.getByLabel('Source namespace',{exact:true}).fill(source);
  await upload(page,'baseline.csv',csv(headers,base));
  await expect(page.getByText('1 valid · 0 quarantined · 1 total')).toBeVisible();
  await page.getByText('Save this validated mapping as a revision').click();
  await page.getByLabel('Revision name').fill('Clinic roster v1');
  await page.getByLabel('Mapping reviewer').fill('Synthetic Reviewer');
  await page.getByLabel('Mapping reason').fill('Required columns reviewed');
  await page.getByRole('button',{name:'Save mapping revision (does not accept)'}).click();
  await expect(page.getByLabel('Saved mapping revision')).toContainText('Clinic roster v1');
  await expect(page.getByText('1 valid · 0 quarantined · 1 total')).toBeVisible();
  await reviewAndAccept(page,'Accept synthetic baseline');
  await expect(page.getByText('committed',{exact:true}).first()).toBeVisible();

  const changed = {...base,phone:'6175550177',extra_note:'new ignored source column'};
  const reordered = ['extra_note','phone','location_id','reference_phone','record_id','npi','provider_name','address','city','state','zip'];
  await upload(page,'changed.csv',csv(reordered,changed));
  await page.getByLabel('Saved mapping revision').selectOption({index:1});
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText(/Applied mapping revision:/)).not.toContainText('None');
  await page.getByText('Comparison with prior source deliveries').click();
  await expect(page.getByText(/Baseline:/)).toContainText('baseline.csv');
  await expect(page.getByText(/Raw rows:/)).toContainText('1');
  await expect(page.getByText(/Unique identities:/)).toContainText('1');
  await page.getByLabel('Filter changes').selectOption('changed');
  await page.getByText(/changed ·/).click();
  await expect(page.getByRole('cell',{name:'6175550100'})).toBeVisible();
  await expect(page.getByRole('cell',{name:'6175550177'})).toBeVisible();
  await page.locator('.ri-comparison').scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath('accepted-delivery-comparison.png')});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Changed phone reviewed');

  // A separate accepted delivery advances the service-owned baseline after this preview.
  const intervening = {...base,phone:'6175550188'};
  const received = await page.request.post(`/api/intakes/files?${new URLSearchParams({filename:'intervening.csv',source,designation:'synthetic',profile:'flat'})}`,{
    data:Buffer.from(csv(headers,intervening)),headers:{'Content-Type':'application/octet-stream'},
  });
  expect(received.ok()).toBeTruthy();
  const receipt = await received.json() as {id:string;attempt_id:string};
  const accepted = await page.request.post(`/api/intakes/${receipt.id}/commit`,{data:{policy:'valid_rows',actor:'Synthetic Reviewer',reason:'Intervening accepted delivery',expected_attempt:receipt.attempt_id}});
  expect(accepted.ok()).toBeTruthy();
  await page.getByRole('button',{name:'Accept valid rows'}).click();
  await expect(page.getByRole('alert').filter({hasText:/baseline changed|refresh comparison/i})).toBeVisible();
  await expect(page.getByLabel('Acceptance / rejection reason')).toHaveValue('Changed phone reviewed');
  await page.getByRole('button',{name:'Refresh comparison'}).click();
  await expect(page.getByText(/Baseline:/)).toContainText('intervening.csv');
  await page.getByRole('button',{name:'Accept valid rows'}).click();
  await expect(page.getByText('committed',{exact:true}).first()).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Evidence packet JSON'}).click();
  const download = await downloadPromise;
  const packet = JSON.parse(await readFile((await download.path())!,'utf8'));
  expect(packet.preview.comparison.baseline.receipt_id).toBe(receipt.id);
  expect(packet.preview.comparison.entries.some((entry: {status:string}) => entry.status === 'changed')).toBeTruthy();

  await upload(page,'missing-header.csv',csv(headers.filter((header) => header !== 'phone'),base));
  await page.getByLabel('Saved mapping revision').selectOption({index:1});
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Required headers missing: phone'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Accept valid rows'})).toBeDisabled();
});
