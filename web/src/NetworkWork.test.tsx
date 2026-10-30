import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { NetworkWorkFilters, NetworkCaseScope } from './NetworkWork';

test('selected network downloads carry only that opaque network id', () => {
  const onNetwork = vi.fn();
  render(<NetworkWorkFilters items={[
    {id:'case-1',network_id:'cedar-id',network_label:'CEDAR',organization_id:'clinic-id',organization_label:'Clinic',practice_location_id:'north-id',location_label:'NORTH'},
    {id:'case-2',network_id:'pine-id',network_label:'PINE',organization_id:'clinic-id',organization_label:'Clinic',practice_location_id:'north-id',location_label:'NORTH'},
  ]} networkId="cedar-id" organizationId="" locationId="" onNetwork={onNetwork} onOrganization={() => {}} onLocation={() => {}} />);
  expect(screen.getByRole('link',{name:'Download selected network XLSX'})).toHaveAttribute('href','/api/work-export.xlsx?network_id=cedar-id');
  expect(screen.getByRole('link',{name:'Download selected network JSON'})).toHaveAttribute('href','/api/work-export.json?network_id=cedar-id');
  expect(screen.getByText(/Shared receipt and attempt payloads/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox',{name:'Network filter'}),{target:{value:'pine-id'}});
  expect(onNetwork).toHaveBeenCalledWith('pine-id');
});

test('participation review displays source comparison without relabeling it human verification', () => {
  render(<NetworkCaseScope scope={{case_id:'case-1',network_id:'cedar-id',network_label:'CEDAR',organization_id:'clinic-id',organization_label:'Clinic',practice_location_id:'north-id',location_label:'NORTH',native_key:'LIST-A'}}
    evidence={{normalized:{participation:{listed_status:'listed',effective_date:'2026-01-01',end_date:null}}}}
    review={[{id:1,status:'blocked_invalid',locator:'row:3',receipt_id:'receipt-2',receipt_label:'changed.csv',payload:{meaning:'Source comparison evidence only',comparison:{status:'blocked_invalid',old:{phone:'5550100000'},new:{phone:'5550100008'},fields:[{field:'phone',old:'5550100000',new:'5550100008'}],previous_locator:'row:2',current_locator:'row:3',previous_receipt_id:'receipt-1'},source_row:{problems:['effective_date must use YYYY-MM-DD']}}}]} />);
  expect(screen.getByText(/Source-listed status and dates are source assertions/)).toBeInTheDocument();
  expect(screen.getByText('5550100008')).toBeInTheDocument();
  expect(screen.getByText(/effective_date must use YYYY-MM-DD/)).toBeInTheDocument();
  expect(screen.getByText(/baseline receipt/)).toBeInTheDocument();
});
