import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { NetworkSetup, RosterConfiguration, emptyRosterBindings, type Catalog, type RosterBindings } from './NetworkSetup';

afterEach(() => vi.unstubAllGlobals());
const catalog: Catalog = {
  organizations:[{id:'clinic-1',label:'Synthetic Clinic',kind:'clinic',actor:'reviewer',reason:'fixture',created_at:'2026-10-30'}],
  networks:[{id:'cedar-1',label:'CEDAR',payer_organization_id:null,actor:'reviewer',reason:'fixture',created_at:'2026-10-30'}],
  locations:[{id:'north-1',label:'NORTH',organization_id:'clinic-1',actor:'reviewer',reason:'fixture',created_at:'2026-10-30'}],
  bindings:[
    {id:'binding-cedar',source:'synthetic-roster',kind:'network',source_key:'CEDAR',target_id:'cedar-1',previous_id:null,revision:1,actor:'reviewer',reason:'fixture',created_at:'2026-10-30',current:true},
    {id:'binding-north',source:'synthetic-roster',kind:'location',source_key:'NORTH',target_id:'north-1',previous_id:null,revision:1,actor:'reviewer',reason:'fixture',created_at:'2026-10-30',current:true},
    {id:'binding-other',source:'different-roster',kind:'network',source_key:'CEDAR',target_id:'cedar-1',previous_id:null,revision:1,actor:'reviewer',reason:'fixture',created_at:'2026-10-30',current:true},
  ],
};

test('network roster selects only reviewed bindings from the exact source', async () => {
  vi.stubGlobal('fetch',vi.fn(async () => new Response(JSON.stringify(catalog))));
  let selected:RosterBindings = emptyRosterBindings();
  const onBindings = vi.fn((value:RosterBindings) => {selected=value;});
  const view = render(<RosterConfiguration source="synthetic-roster" kind="network" bindings={selected} fixedNetworkBindingId="" busy={false}
    onKind={() => {}} onBindings={onBindings} onFixedNetworkBindingId={() => {}} />);
  const networkGroup = await screen.findByRole('group',{name:'network source codes'});
  expect(within(networkGroup).getAllByRole('checkbox')).toHaveLength(1);
  expect(within(networkGroup).getByRole('checkbox',{name:/CEDAR → CEDAR/})).not.toBeChecked();
  expect(screen.getByRole('combobox',{name:/Fixed single-network binding/})).toHaveValue('');
  fireEvent.click(within(networkGroup).getByRole('checkbox',{name:/CEDAR → CEDAR/}));
  expect(onBindings).toHaveBeenCalledWith({network:{CEDAR:'binding-cedar'},organization:{},location:{}});
  view.rerender(<RosterConfiguration source="synthetic-roster" kind="network" bindings={selected} fixedNetworkBindingId="" busy={false}
    onKind={() => {}} onBindings={onBindings} onFixedNetworkBindingId={() => {}} />);
  expect(screen.getByRole('combobox',{name:/Fixed single-network binding/}).querySelectorAll('option')).toHaveLength(2);
});

test('catalog setup creates explicit records without importing or accepting a delivery', async () => {
  const calls:{url:string;body:Record<string,unknown>}[]=[];
  vi.stubGlobal('fetch',vi.fn(async (url:string,init?:RequestInit) => {
    if (init?.method === 'POST') {
      calls.push({url,body:JSON.parse(String(init.body))});
      return new Response(JSON.stringify({id:'new-organization'}));
    }
    return new Response(JSON.stringify(catalog));
  }));
  render(<NetworkSetup source="synthetic-roster" />);
  fireEvent.click(screen.getByText('Organization and network setup'));
  await screen.findByText(/Current source bindings/);
  fireEvent.change(screen.getByLabelText('Catalog reviewer'),{target:{value:'Synthetic Reviewer'}});
  fireEvent.change(screen.getByLabelText('Catalog reason'),{target:{value:'Reviewed source codebook'}});
  fireEvent.change(screen.getByLabelText('Organization label'),{target:{value:'Synthetic Payer'}});
  fireEvent.change(screen.getByLabelText('Organization kind'),{target:{value:'payer'}});
  fireEvent.click(screen.getByRole('button',{name:'Create organization'}));
  await waitFor(() => expect(calls).toEqual([{url:'/api/catalog/organizations',body:{label:'Synthetic Payer',kind:'payer',actor:'Synthetic Reviewer',reason:'Reviewed source codebook'}}]));
  expect(calls.some((call) => /intakes|commit/.test(call.url))).toBe(false);
});

test('catalog controls stay frozen until an in-flight create and refresh finish', async () => {
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  vi.stubGlobal('fetch',vi.fn(async (_url:string,init?:RequestInit) => {
    if (init?.method === 'POST') await pending;
    return new Response(JSON.stringify(init?.method === 'POST' ? {id:'new-org'} : catalog));
  }));
  render(<NetworkSetup source="synthetic-roster" />);
  fireEvent.click(screen.getByText('Organization and network setup'));
  await screen.findByText(/Current source bindings/);
  fireEvent.change(screen.getByLabelText('Catalog reviewer'),{target:{value:'Reviewer'}});
  fireEvent.change(screen.getByLabelText('Catalog reason'),{target:{value:'Reviewed fixture'}});
  fireEvent.change(screen.getByLabelText('Organization label'),{target:{value:'New payer'}});
  fireEvent.click(screen.getByRole('button',{name:'Create organization'}));
  await waitFor(() => expect(screen.getByLabelText('Organization label')).toBeDisabled());
  expect(screen.getByLabelText('Network label')).toBeDisabled();
  expect(screen.getByLabelText('Location label')).toBeDisabled();
  expect(screen.getByLabelText('Binding kind')).toBeDisabled();
  expect(screen.getByLabelText('Catalog reviewer')).toBeDisabled();
  release();
  await waitFor(() => expect(screen.getByLabelText('Organization label')).toBeEnabled());
});
