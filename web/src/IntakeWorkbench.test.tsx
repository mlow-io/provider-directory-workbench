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
