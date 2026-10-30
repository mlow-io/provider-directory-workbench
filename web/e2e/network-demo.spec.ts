import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

const sample = (page:Page) => page.getByRole('combobox',{name:'Synthetic sample'});
async function loadSample(page:Page,id:string,name:string) {
  await sample(page).selectOption(id);
  await page.getByRole('button',{name:'Load synthetic sample'}).click();
  await expect(page.getByRole('heading',{name})).toBeVisible();
}
async function selectRevision(page:Page,name:string) {
  const selector = page.getByRole('combobox',{name:'Saved mapping revision'});
  const optionValue = () => selector.evaluate((element,needle) => [...(element as HTMLSelectElement).options].find((option) => option.textContent?.includes(needle))?.value ?? '',name);
  await expect.poll(optionValue).not.toBe('');
  const id = await optionValue();
  expect(id,`saved mapping ${name} should be available`).not.toBe('');
  await selector.selectOption(id);
  await expect(selector).toHaveValue(id);
  return id;
}
async function accept(page:Page,reason:string) {
  await page.getByLabel('Reviewer',{exact:true}).first().fill('Synthetic Reviewer');
  await page.getByLabel('Acceptance / rejection reason').fill(reason);
  await page.getByRole('button',{name:'Accept valid rows'}).click();
}
async function screenshotAtBothSizes(page:Page,info:import('@playwright/test').TestInfo,name:string) {
  await page.setViewportSize({width:1440,height:960});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath(`${name}-desktop.png`),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path:info.outputPath(`${name}-phone.png`),fullPage:true});
  await page.setViewportSize({width:1440,height:960});
}
async function downloadedJson(page:Page,label:string) {
  const pending=page.waitForEvent('download');
  await page.getByRole('link',{name:label}).click();
  return JSON.parse(await readFile((await (await pending).path())!,'utf8'));
}
async function openMapping(page:Page) {
  const summary=page.getByText('Column mapping and parsing',{exact:true});
  if (!(await summary.locator('..').evaluate((element) => (element as HTMLDetailsElement).open))) await summary.click();
}

test('guided synthetic network path keeps setup, mapping, acceptance and review distinct',async ({page},info) => {
  if (info.project.name === 'mobile') {
    // The demo has one fixed source/scope. The wide run exercises mutations at both viewport widths;
    // this project independently checks that the entry controls remain usable on a compact screen.
    await page.goto('/?view=intake');
    await expect(page.getByRole('button',{name:'Prepare synthetic network catalog'})).toBeVisible();
    await sample(page).selectOption('network-baseline');
    await expect(page.getByText(/Prepare explicit synthetic organization/)).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
    await page.screenshot({path:info.outputPath('network-entry-mobile-project.png'),fullPage:true});
    return;
  }
  test.setTimeout(120_000);
  await page.goto('/?view=intake');
  const before = await (await page.request.get('/api/intakes')).json();
  const setupResponse = page.waitForResponse((response) => response.url().endsWith('/api/demo/network-setup'));
  await page.getByRole('button',{name:'Prepare synthetic network catalog'}).click();
  const setup = await setupResponse;
  expect(setup.ok()).toBeTruthy();
  const prepared = await setup.json() as {notice:string;catalog:{networks:{id:string;label:string}[]}};
  await expect(page.getByRole('status').filter({hasText:prepared.notice})).toBeVisible();
  const after = await (await page.request.get('/api/intakes')).json();
  expect(after.items).toHaveLength(before.items.length);
  await screenshotAtBothSizes(page,info,'network-entry');

  await loadSample(page,'network-baseline','synthetic-network-baseline.csv');
  await expect(page.getByText('Use suggested network scope')).toBeVisible();
  await page.getByRole('button',{name:'Use suggested network scope'}).click();
  await openMapping(page);
  await expect(page.getByRole('combobox',{name:'Roster kind'})).toHaveValue('network');
  await page.getByRole('button',{name:'Save mapping and reprocess'}).click();
  await expect(page.getByText('3 valid · 0 quarantined · 3 total')).toBeVisible();
  await page.getByText('Save this validated mapping as a revision').click();
  await page.getByLabel('Revision name').fill('Guided network mapping v1');
  await page.getByLabel('Mapping reviewer').fill('Synthetic Reviewer');
  await page.getByLabel('Mapping reason').fill('Reviewed CEDAR/PINE and NORTH/SOUTH codebook');
  await page.getByRole('button',{name:'Save mapping revision (does not accept)'}).click();
  const firstRevision = await selectRevision(page,'Guided network mapping v1');
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('3 valid · 0 quarantined · 3 total')).toBeVisible();
  await accept(page,'Accept three reviewed synthetic network assertions');
  await expect(page.getByRole('heading',{name:'Source observations and relationships'})).toBeVisible();
  const baselinePacket = await downloadedJson(page,'Evidence packet JSON');
  expect(baselinePacket.observations).toHaveLength(3);
  expect(baselinePacket.cases.filter((item:{field_name:string}) => item.field_name === 'participation')).toHaveLength(3);

  const pineId = prepared.catalog.networks.find((item) => item.label === 'Synthetic PINE')!.id;
  const cedarId = prepared.catalog.networks.find((item) => item.label === 'Synthetic CEDAR')!.id;
  const pineInitial = (await (await page.request.get(`/api/work?network_id=${pineId}`)).json()).items[0];
  await page.request.post(`/api/work/${pineInitial.id}/events`,{data:{action:'assign',owner:'Baseline steward',actor:'Synthetic Reviewer',reason:'Follow source status manually',expected_version:0}});
  const initialHumanState = await (await page.request.get(`/api/work/${pineInitial.id}`)).json();
  expect(initialHumanState.owner).toBe('Baseline steward');

  await loadSample(page,'network-changed','synthetic-network-changed.csv');
  await selectRevision(page,'Guided network mapping v1');
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('2 valid · 3 quarantined · 5 total')).toBeVisible();
  await page.getByText('Comparison with prior source deliveries').click();
  for (const [status,count] of [['new',1],['changed',1],['blocked invalid',2],['unresolved',1],['missing',1]] as const)
    await expect(page.locator('.ri-counts')).toContainText(`${status}: ${count}`);
  await expect(page.getByText(/Raw rows:/)).toContainText('5');
  await screenshotAtBothSizes(page,info,'network-comparison');
  await page.setViewportSize({width:390,height:844});
  await accept(page,'Accept two valid rows; retain conflicting, unknown and missing evidence');
  await expect(page.getByRole('heading',{name:'Linked cases'})).toBeVisible();
  const changedPacket = await downloadedJson(page,'Evidence packet JSON');
  expect(changedPacket.preview.comparison.entries.filter((item:{status:string}) => item.status === 'blocked_invalid')).toHaveLength(2);
  expect(changedPacket.preview.comparison.missing_from_this_delivery).toBe(1);
  const afterChanged = await (await page.request.get(`/api/work/${pineInitial.id}`)).json();
  expect([afterChanged.status,afterChanged.owner,afterChanged.version]).toEqual([initialHumanState.status,initialHumanState.owner,initialHumanState.version]);

  await page.goto('/?view=work');
  await page.getByRole('combobox',{name:'Network filter'}).selectOption(pineId);
  await page.getByRole('button',{name:/Quarantined participation requires review/}).click();
  await expect(page.getByRole('heading',{name:'Network participation scope'})).toBeVisible();
  await page.getByRole('combobox',{name:'Action',exact:true}).selectOption('assign');
  await page.getByLabel('actor *').fill('Synthetic Reviewer');
  await page.getByLabel('reason *').fill('Review contradictory source status');
  await page.getByLabel('owner *').fill('Network coordinator');
  await page.getByRole('button',{name:'Save review event'}).click();
  await expect(page.getByText(/Current owner: Network coordinator/)).toBeVisible();
  await screenshotAtBothSizes(page,info,'network-work');
  await page.setViewportSize({width:390,height:844});
  const networkSnapshot = await downloadedJson(page,'Download selected network JSON');
  expect(networkSnapshot.network_id).toBe(pineId);
  expect(networkSnapshot.review_evidence.some((item:{status:string}) => item.status === 'blocked_invalid')).toBeTruthy();
  expect(networkSnapshot.participations.every((item:{network_id:string}) => item.network_id === pineId)).toBeTruthy();
  const networkXlsxPromise = page.waitForEvent('download');
  await page.getByRole('link',{name:'Download selected network XLSX'}).click();
  const networkXlsx = await networkXlsxPromise;
  const networkXlsxPath=info.outputPath('network-demo-scoped.xlsx');
  await networkXlsx.saveAs(networkXlsxPath);
  const workbookSummary = JSON.parse(execFileSync('python3',['-c',`import json,sys\nfrom openpyxl import load_workbook\nw=load_workbook(sys.argv[1],read_only=True,data_only=True)\ndef rows(n):return list(w[n].values)[1:]\nprint(json.dumps({'cases':len(rows('Cases')),'review':len(rows('Review evidence')),'network_ids':[r[1] for r in rows('Catalog') if r[0]=='networks']}))\nw.close()`,networkXlsxPath],{encoding:'utf8'}));
  expect(workbookSummary.cases).toBeGreaterThanOrEqual(2);
  expect(workbookSummary.review).toBeGreaterThanOrEqual(1);
  expect(workbookSummary.network_ids).toContain(pineId);
  expect(workbookSummary.network_ids).not.toContain(cedarId);

  await page.goto('/?view=intake');
  await loadSample(page,'network-header-drift','synthetic-network-header-drift.csv');
  await selectRevision(page,'Guided network mapping v1');
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Required headers missing: phone'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Accept valid rows'})).toBeDisabled();
  await openMapping(page);
  await page.getByRole('combobox',{name:/^phone \*/}).selectOption('Published phone');
  await page.getByRole('button',{name:'Save mapping and reprocess'}).click();
  await expect(page.getByText('2 valid · 3 quarantined · 5 total')).toBeVisible();
  await page.getByText('Save this validated mapping as a revision').click();
  await page.getByLabel('Revision name').fill('Network headers v2');
  await page.getByLabel('Mapping reviewer').fill('Synthetic Reviewer');
  await page.getByLabel('Mapping reason').fill('Reviewed renamed phone header');
  await page.getByRole('button',{name:'Save mapping revision (does not accept)'}).click();
  const secondRevision = await selectRevision(page,'Network headers v2');
  expect(secondRevision).not.toBe(firstRevision);
  await expect(page.getByRole('combobox',{name:'Saved mapping revision'})).toContainText('Guided network mapping v1');
  await page.getByRole('button',{name:'Apply saved mapping and reprocess'}).click();
  await expect(page.getByText('2 valid · 3 quarantined · 5 total')).toBeVisible();
  await accept(page,'Accept valid renamed-header rows after separate review');
  await expect(page.getByRole('heading',{name:'Linked cases'})).toBeVisible();
  const afterDrift = await (await page.request.get(`/api/work/${pineInitial.id}`)).json();
  expect([afterDrift.status,afterDrift.owner,afterDrift.version]).toEqual([initialHumanState.status,initialHumanState.owner,initialHumanState.version]);
  const saved=(await (await page.request.get(`/api/intakes/${afterDrift.evidence.receipt_id}/saved-mappings`)).json()).items;
  expect(saved.some((item:{id:string;settings:{mapping:{phone:string}}}) => item.id === firstRevision && item.settings.mapping.phone === 'phone')).toBeTruthy();
  expect(saved.some((item:{id:string;settings:{mapping:{phone:string}}}) => item.id === secondRevision && item.settings.mapping.phone === 'Published phone')).toBeTruthy();
});
