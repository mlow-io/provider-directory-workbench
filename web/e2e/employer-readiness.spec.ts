import { expect, test } from '@playwright/test';
import { execFileSync } from 'node:child_process';

// Inspect the actual browser download with the existing openpyxl dependency.
function inspectWorkbook(filename: string) {
  return JSON.parse(execFileSync('python3', ['-c', `
import json,sys
from openpyxl import load_workbook
w=load_workbook(sys.argv[1],data_only=False)
result={}
for name in ['Cases','Evidence','Receipts','Decisions']:
 rows=list(w[name].values)
 result[name]=[dict(zip(rows[0],r)) for r in rows[1:]]
result['formula_count']=sum(c.data_type=='f' for s in w for row in s for c in row)
print(json.dumps(result))
w.close()
`, filename], { encoding: 'utf8' }));
}

test('guided offline sample requires mapping review and downloads complete read-only work handoff', async ({ page, request }, info) => {
  await page.goto('/?view=intake');
  await expect(page.getByRole('heading', {name: 'Start with a clinic roster'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'Load synthetic sample'})).toBeInViewport();
  await page.screenshot({path: info.outputPath('guided-entry.png')});
  await page.getByRole('button', {name: 'Load synthetic sample'}).click();
  await expect(page.getByText('Synthetic example — no real clinicians or payer updates.')).toBeVisible();
  const suggest = page.getByRole('button', {name: 'Use suggested columns'});
  // A later viewport replays the same fixed synthetic source; committed mapping is reused.
  if (await page.getByText('needs mapping', {exact:true}).isVisible()) {
    await expect(page.getByLabel('Header row', {exact:true})).toHaveValue('2');
    await expect(page.getByRole('button', {name:'Accept valid rows'})).toBeDisabled();
    await suggest.click();
    await expect(page.getByRole('combobox', {name:/^npi \*/})).toHaveValue('Registry number');
    await expect(page.getByRole('button', {name:'Accept valid rows'})).toBeDisabled();
    await page.getByRole('button', {name:'Save mapping and reprocess'}).click();
  }
  await expect(page.getByText('2 valid · 1 quarantined · 3 total')).toBeVisible();
  await page.getByText('Clinic roster!5 · Quarantined', {exact:true}).click();
  await expect(page.locator('.iw-preview')).toContainText('Phone must contain ten digits');
  await page.locator('#intake-receipt-detail').scrollIntoViewIfNeeded();
  await page.screenshot({path: info.outputPath('guided-preview.png')});
  await page.getByLabel('Reviewer', {exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Reviewed mapping and retained malformed row');
  await page.getByRole('button', {name:'Accept valid rows'}).click();
  await expect(page.getByRole('heading', {name:'Linked cases'})).toBeVisible();
  const beforeRepeat = (await (await request.get('/api/work')).json()).items.filter((c: {source:string})=>c.source==='synthetic-demo');
  expect(beforeRepeat).toHaveLength(2);
  await page.getByRole('button', {name:'Load synthetic sample'}).click();
  await expect(page.getByText(/Repeat delivery of/)).toBeVisible();
  await page.getByLabel('Reviewer', {exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill('Accidental repeat retains scoped work');
  await page.getByRole('button', {name:'Accept valid rows'}).click();
  await expect(page.getByText('duplicate delivery', {exact:true})).toBeVisible();
  expect((await (await request.get('/api/work')).json()).items.filter((c: {source:string})=>c.source==='synthetic-demo')).toEqual(beforeRepeat);

  await page.getByRole('link', {name:'Open durable work queue →'}).click();
  await page.getByLabel('Search work').fill('synthetic-demo:NORTH');
  await expect(page.locator('.iw-list li button')).toHaveCount(1);
  await page.locator('.iw-list li button').click();
  await page.getByRole('combobox', {name:'Action', exact:true}).selectOption('assign');
  await page.getByLabel('actor *', {exact:true}).fill('Synthetic Reviewer');
  await page.getByLabel('reason *', {exact:true}).fill('Hand off NORTH phone request');
  await page.getByLabel('owner *', {exact:true}).fill(`Demo Owner ${info.project.name}`);
  await page.getByLabel('follow up', {exact:true}).fill('2026-11-01');
  await page.getByRole('button', {name:'Save review event'}).click();
  await expect(page.getByLabel('reason *', {exact:true})).toHaveValue('');
  const casesBefore = (await (await request.get('/api/work')).json()).items;
  const north = casesBefore.find((c: {location_id:string})=>c.location_id==='synthetic-demo:NORTH');
  const detailBefore = await (await request.get(`/api/work/${north.id}`)).json();
  await page.getByRole('link', {name:'Download case XLSX'}).scrollIntoViewIfNeeded();
  await page.screenshot({path:info.outputPath('guided-work.png')});
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', {name:'Download case XLSX'}).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('durable-work-handoff.xlsx');
  const saved = info.outputPath('selected-case.xlsx');
  await download.saveAs(saved);
  const workbook = inspectWorkbook(saved);
  expect(workbook.Cases).toHaveLength(1);
  expect(workbook.Cases[0]).toMatchObject({case_id:north.id, location_id:'synthetic-demo:NORTH', owner:`Demo Owner ${info.project.name}`, npi:'1234567890', listed_value:'6175550100', requested_value:'6175550199'});
  expect(workbook.Evidence[0]).toMatchObject({role:'initial', row_locator:'Clinic roster!3', zip:'02108', source:'synthetic-demo', designation:'synthetic'});
  expect(workbook.Receipts.some((r:{duplicate_of:unknown})=>r.duplicate_of)).toBeTruthy();
  expect(workbook.Decisions.at(-1)).toMatchObject({action:'assign',reason:'Hand off NORTH phone request'});
  expect(workbook.formula_count).toBe(0);
  // Download all work while a filter hides every item: scope must remain explicit and complete.
  await page.getByLabel('Search work').fill('no-matching-case');
  await expect(page.getByText('No work matches these filters.')).toBeVisible();
  await expect(page.getByText('Includes every durable case, evidence row and decision; ignores the filters below.')).toBeVisible();
  const allPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download all work XLSX'}).click();
  const allSaved = info.outputPath('all-work.xlsx');
  await (await allPromise).saveAs(allSaved);
  expect(inspectWorkbook(allSaved).Cases).toHaveLength(casesBefore.length);
  expect(await (await request.get(`/api/work/${north.id}`)).json()).toEqual(detailBefore);
  expect((await (await request.get('/api/work')).json()).items).toEqual(casesBefore);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
