import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { IntakeWorkbench } from './IntakeWorkbench';

afterEach(() => {
  vi.unstubAllGlobals();
  history.replaceState(null, '', '/');
});

test('CMS lookup sends its supported NPI query without NPPES-only fields', async () => {
  const lookups: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/intakes/lookups') {
      lookups.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify({id:'synthetic-reference'}),{status:200});
    }
    return new Response(JSON.stringify(url === '/api/intakes' ? {items:[]} : {id:'synthetic-reference',label:'Synthetic CMS response',state:'preview_ready',metadata:{},attempts:[],observations:[],linked_cases:[]}),{status:200});
  }));
  render(<IntakeWorkbench page='intake' />);
  fireEvent.click(screen.getByText('Look up a public reference'));
  fireEvent.change(screen.getByRole('combobox',{name:/^Reference$/}),{target:{value:'cms'}});
  fireEvent.change(screen.getByLabelText('NPI (optional)'),{target:{value:'1234567890'}});
  fireEvent.click(screen.getByRole('button',{name:'Fetch reference'}));
  await waitFor(()=>expect(lookups).toEqual([{source:'cms',query:{npi:'1234567890',limit:10}}]));
  await screen.findByRole('heading',{name:'Synthetic CMS response'});
});

test('sample columns fill an editable form without accepting or saving until the reviewer acts', async () => {
  const calls: {url: string; body: Record<string, unknown>}[] = [];
  const mapping = {
    npi: 'Registry number', provider_name: 'Clinician', address: 'Street', city: 'Town',
    state: 'Region', zip: 'Postal', phone: 'Listed phone', record_id: 'Roster key',
    location_id: 'Site key', reference_phone: 'Requested phone',
  };
  const receipt = {
    id: 'sample-receipt', label: 'synthetic-clinic.xlsx', source: 'synthetic-demo', designation: 'synthetic',
    state: 'needs_mapping', attempt_id: 'attempt-1',
    metadata: {demo_sample: 'clinic-workbook', suggested_mapping: mapping},
    attempts: [{id: 'attempt-1', spec: {header_row: 2, sheet: 'Clinic roster'}}],
    preview: {headers: Object.values(mapping), mapping: {}, state: 'needs_mapping', rows: [], valid_count: 0},
    observations: [], linked_cases: [],
  };
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') calls.push({url, body: JSON.parse(String(init.body))});
    if (url === '/api/demo/samples') return new Response(JSON.stringify({items: [
      {id: 'clinic-workbook', label: 'Synthetic clinic workbook', description: 'Two locations and one malformed row.'},
    ]}));
    if (url === '/api/intakes') return new Response(JSON.stringify({items: []}));
    return new Response(JSON.stringify(receipt));
  }));
  render(<IntakeWorkbench page='intake' />);
  fireEvent.click(await screen.findByRole('button', {name: 'Load synthetic sample'}));
  await screen.findByRole('heading', {name: 'synthetic-clinic.xlsx'});
  await waitFor(() => expect(screen.getByLabelText('Header row')).toHaveValue(2));
  expect(screen.getByRole('button', {name: 'Accept valid rows'})).toBeDisabled();
  expect(screen.getByLabelText('npi *')).toHaveValue('');
  fireEvent.click(screen.getByRole('button', {name: 'Use suggested columns'}));
  expect(screen.getByLabelText('npi *')).toHaveValue('Registry number');
  expect(screen.getByLabelText('location id (optional)')).toHaveValue('Site key');
  expect(calls).toEqual([{url: '/api/demo/samples/clinic-workbook', body: {}}]);
  fireEvent.change(screen.getByLabelText('npi *'), {target: {value: 'Clinician'}});
  fireEvent.click(screen.getByRole('button', {name: 'Save mapping and reprocess'}));
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[1]).toMatchObject({url: '/api/intakes/sample-receipt/mapping', body: {
    header_row: 2, mapping: {...mapping, npi: 'Clinician'},
  }});
  expect(calls.some(call => call.url.endsWith('/commit'))).toBe(false);
  expect(screen.getByLabelText('Synthetic sample next step')).toHaveTextContent('no real clinicians');
});

test('ordinary uploads remain available when synthetic sample mode is disabled', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({items: []}))));
  render(<IntakeWorkbench page='intake' />);
  await screen.findByText('No deliveries yet. Upload a file to begin.');
  expect(screen.queryByRole('button', {name: 'Load synthetic sample'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('Source file')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: 'Upload and preview'})).toBeDisabled();
});

test('XLSX links distinguish the full queue from the selected case regardless of filters', async () => {
  history.replaceState(null, '', '/?view=work&case=case-1&search=not-matching');
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
    url === '/api/work' ? {items: []} : {
      id: 'case-1', provider_name: 'Synthetic clinician', kind: 'correction', status: 'new', version: 0,
      location_id: 'synthetic-demo:NORTH', evidence: {}, history: [], later_evidence: [],
    },
  ))));
  render(<IntakeWorkbench page='work' />);
  expect(screen.getByRole('link', {name: 'Download all work XLSX'})).toHaveAttribute('href', '/api/work-export.xlsx');
  expect(screen.getByText(/ignores the filters below/)).toBeInTheDocument();
  expect(await screen.findByRole('link', {name: 'Download case XLSX'})).toHaveAttribute('href', '/api/work-export.xlsx?case_id=case-1');
});

test('only a reviewed empty full network snapshot can accept absence evidence', async () => {
  const commits: Record<string,unknown>[] = [];
  const receipt = {
    id:'empty-network',label:'empty-network.csv',source:'synthetic-network',designation:'synthetic',state:'preview_ready',attempt_id:'attempt-empty',
    metadata:{completeness:'full'},attempts:[{id:'attempt-empty',spec:{roster_kind:'network',mapping:{},bindings:{network:{},location:{},organization:{}}}}],
    preview:{state:'preview_ready',total:0,valid_count:0,quarantined_count:0,rows:[],mapping:{},comparison:{baseline:{attempt_id:'prior',receipt_id:'prior-receipt',label:'prior.csv',committed_at:'2026-10-30'},missing_from_this_delivery:3,entries:[]}},
    observations:[],linked_cases:[],
  };
  vi.stubGlobal('fetch',vi.fn(async (url:string,init?:RequestInit) => {
    if (url === '/api/intakes') return new Response(JSON.stringify({items:[{id:receipt.id,label:receipt.label,source:receipt.source,state:receipt.state}]}));
    if (url === '/api/demo/samples') return new Response(JSON.stringify({items:[]}));
    if (url.endsWith('/saved-mappings')) return new Response(JSON.stringify({items:[]}));
    if (url.endsWith('/commit')) {commits.push(JSON.parse(String(init?.body)));return new Response(JSON.stringify({...receipt,state:'committed'}));}
    if (url === '/api/catalog') return new Response(JSON.stringify({organizations:[],networks:[],locations:[],bindings:[]}));
    return new Response(JSON.stringify(receipt));
  }));
  render(<IntakeWorkbench page="intake" />);
  fireEvent.click(await screen.findByRole('button',{name:/empty-network.csv/}));
  const accept = await screen.findByRole('button',{name:'Accept empty snapshot as absence evidence'});
  expect(accept).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Reviewer',{exact:true}),{target:{value:'Synthetic Reviewer'}});
  fireEvent.change(screen.getByLabelText('Acceptance / rejection reason'),{target:{value:'Full scoped empty file reviewed'}});
  expect(accept).toBeEnabled();
  fireEvent.click(accept);
  await waitFor(() => expect(commits).toEqual([{policy:'valid_rows',actor:'Synthetic Reviewer',reason:'Full scoped empty file reviewed',expected_attempt:'attempt-empty'}]));
});
