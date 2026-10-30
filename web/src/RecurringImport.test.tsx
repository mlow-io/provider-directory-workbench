import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { RecurringImport, type DeliveryComparison } from './RecurringImport';

afterEach(() => vi.unstubAllGlobals());

const comparison: DeliveryComparison = {
  baseline: {attempt_id:'prior-attempt',receipt_id:'prior-receipt',label:'prior.csv',committed_at:'2026-10-30T12:00:00Z',mapping_revision_id:'revision-1'},
  raw_row_count:3, unique_identity_count:2,new:0,changed:1,unchanged:1,unresolved:0,blocked_invalid:1,missing_from_this_delivery:0,
  entries:[
    {key:'NORTH',status:'changed',old:{phone:'6175550100'},new:{phone:'6175550177'},fields:[{field:'phone',old:'6175550100',new:'6175550177'}],previous_locator:'row:2',current_locator:'row:3',interpretation_changed:false},
    {key:null,status:'blocked_invalid',old:null,new:null,fields:[],current_locator:'row:4'},
  ],
};

test('saved mapping and comparison are review steps separate from acceptance', async () => {
  const calls: {url:string; body:Record<string,unknown>}[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      calls.push({url,body:JSON.parse(String(init.body))});
      return new Response(JSON.stringify({id:'revision-2',name:'Clinic columns'}));
    }
    return new Response(JSON.stringify({items:[{id:'revision-1',name:'Clinic columns',source:'clinic',profile:'flat',scope:null,settings:{},required_headers:['NPI','Phone'],actor:'Reviewer',reason:'Reviewed',created_at:'2026-10-30'}]}));
  }));
  const onRun = vi.fn(async () => {});
  const onChanged = vi.fn(async () => {});
  render(<RecurringImport receiptId="receipt-1" state="preview_ready" attemptId="attempt-1" appliedRevisionId={null}
    comparison={comparison} effectiveMapping={{npi:'NPI'}} parsing={{sheet:'',header_row:1,encoding:'utf-8-sig',delimiter:','}}
    busy={false} onRun={onRun} onChanged={onChanged} />);
  fireEvent.click(await screen.findByText('Comparison with prior source deliveries'));
  expect(screen.getByText(/Raw rows:/)).toHaveTextContent('3');
  expect(screen.getByText(/Unique identities:/)).toHaveTextContent('2');
  expect(screen.getByText('6175550177')).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Filter changes'),{target:{value:'blocked_invalid'}});
  expect(screen.queryByText('6175550177')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Refresh comparison'}));
  expect(onRun).toHaveBeenCalledWith('mapping',{mapping:{npi:'NPI'},sheet:'',header_row:1,encoding:'utf-8-sig',delimiter:','});
  fireEvent.change(screen.getByLabelText('Revision name'),{target:{value:'Clinic columns'}});
  fireEvent.change(screen.getByLabelText('Mapping reviewer'),{target:{value:'Synthetic Reviewer'}});
  fireEvent.change(screen.getByLabelText('Mapping reason'),{target:{value:'Reviewed required headers'}});
  fireEvent.click(screen.getByRole('button',{name:'Save mapping revision (does not accept)'}));
  await waitFor(() => expect(calls).toEqual([{url:'/api/intakes/receipt-1/saved-mappings',body:{name:'Clinic columns',actor:'Synthetic Reviewer',reason:'Reviewed required headers',expected_attempt:'attempt-1'}}]));
  expect(onChanged).toHaveBeenCalled();
  expect(calls.some((call) => call.url.endsWith('/commit'))).toBe(false);
  fireEvent.change(screen.getByLabelText('Saved mapping revision'),{target:{value:'revision-1'}});
  fireEvent.click(screen.getByRole('button',{name:'Apply saved mapping and reprocess'}));
  expect(onRun).toHaveBeenCalledWith('mapping',{mapping_revision_id:'revision-1'});
});

test('applied revision refresh sends only the revision id', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({items:[]}))));
  const onRun = vi.fn(async () => {});
  render(<RecurringImport receiptId="receipt-2" state="preview_ready" attemptId="attempt-2" appliedRevisionId="revision-3"
    comparison={comparison} effectiveMapping={{npi:'NPI'}} parsing={{sheet:'',header_row:1,encoding:'utf-8-sig',delimiter:','}}
    busy={false} onRun={onRun} onChanged={async () => {}} />);
  fireEvent.click(screen.getByText('Comparison with prior source deliveries'));
  fireEvent.click(screen.getByRole('button',{name:'Refresh comparison'}));
  expect(onRun).toHaveBeenCalledWith('mapping',{mapping_revision_id:'revision-3'});
});
