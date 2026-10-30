import './network-work.css';

type QueueScope = {
  network_id?:string|null;network_label?:string|null;
  organization_id?:string|null;organization_label?:string|null;
  practice_location_id?:string|null;location_label?:string|null;
};
export type CaseScope = QueueScope & {case_id:string;native_key:string};
export type ReviewEntry = {
  id:number;status:string;locator:string;receipt_id:string;receipt_label:string;
  receipt_metadata?:Record<string,unknown>;
  payload?:{
    assertion?:string;meaning?:string;
    comparison?:{status:string;old?:Record<string,unknown>|null;new?:Record<string,unknown>|null;fields?:{field:string;old:unknown;new:unknown}[];previous_locator?:unknown;current_locator?:unknown;previous_receipt_id?:string|null};
    source_row?:{problems?:string[];original?:Record<string,unknown>}|null;
  };
};
export type NetworkWorkItem = QueueScope & {id:string};
const display = (value:unknown) => value == null || value === '' ? 'Unknown' : typeof value === 'string' ? value : JSON.stringify(value);
const options = (items:NetworkWorkItem[], idKey:keyof QueueScope, labelKey:keyof QueueScope) => {
  const values = new Map<string,string>();
  for (const item of items) {
    const id = item[idKey];
    if (id) values.set(id, String(item[labelKey] || id));
  }
  return [...values].sort((a,b) => a[1].localeCompare(b[1]));
};
export function NetworkWorkFilters({items,networkId,organizationId,locationId,onNetwork,onOrganization,onLocation}: {
  items:NetworkWorkItem[];networkId:string;organizationId:string;locationId:string;
  onNetwork:(value:string)=>void;onOrganization:(value:string)=>void;onLocation:(value:string)=>void;
}) {
  return <>
    <div className="iw-form nw-filters">
      <label>Network filter<select value={networkId} onChange={(event) => onNetwork(event.target.value)}>
        <option value="">All networks</option>{options(items,'network_id','network_label').map(([id,label]) => <option key={id} value={id}>{label} · {id}</option>)}
      </select></label>
      <label>Organization filter<select value={organizationId} onChange={(event) => onOrganization(event.target.value)}>
        <option value="">All organizations</option>{options(items,'organization_id','organization_label').map(([id,label]) => <option key={id} value={id}>{label} · {id}</option>)}
      </select></label>
      <label>Practice location filter<select value={locationId} onChange={(event) => onLocation(event.target.value)}>
        <option value="">All practice locations</option>{options(items,'practice_location_id','location_label').map(([id,label]) => <option key={id} value={id}>{label} · {id}</option>)}
      </select></label>
    </div>
    {networkId && <div className="nw-export">
      <p>Selected network: <strong>{options(items,'network_id','network_label').find(([id]) => id === networkId)?.[1] ?? networkId}</strong>. These downloads contain that network's operational cases, evidence and participation assertions. Shared receipt and attempt payloads are labeled source context and may contain other rows.</p>
      <div className="iw-links">
        <a href={`/api/work-export.xlsx?${new URLSearchParams({network_id:networkId})}`} download>Download selected network XLSX</a>
        <a href={`/api/work-export.json?${new URLSearchParams({network_id:networkId})}`} download>Download selected network JSON</a>
      </div>
    </div>}
  </>;
}
export function NetworkCaseScope({scope,review,evidence}: {scope:CaseScope|null|undefined;review:ReviewEntry[]|undefined;evidence?:{normalized?:Record<string,unknown>}}) {
  if (!scope) return null;
  const participation = evidence?.normalized?.participation as Record<string,unknown>|undefined;
  return <section className="nw-case" aria-label="Network participation scope">
    <h3>Network participation scope</h3>
    <dl className="iw-facts">
      <dt>Network</dt><dd>{display(scope.network_label)} · {scope.network_id}</dd>
      <dt>Organization</dt><dd>{display(scope.organization_label)}{scope.organization_id ? ` · ${scope.organization_id}` : ''}</dd>
      <dt>Practice location</dt><dd>{display(scope.location_label)} · {scope.practice_location_id}</dd>
      <dt>Source-native key</dt><dd>{scope.native_key}</dd>
      <dt>Source-listed status</dt><dd>{display(participation?.listed_status)}</dd>
      <dt>Source effective date</dt><dd>{display(participation?.effective_date)}</dd>
      <dt>Source end date</dt><dd>{display(participation?.end_date)}</dd>
    </dl>
    <p className="iw-muted">Source-listed status and dates are source assertions. Human review state, owner, actions and verification are recorded separately below. Later evidence never changes those decisions automatically.</p>
    {review && review.length > 0 && <details open>
      <summary>Participation review evidence ({review.length})</summary>
      <ol className="nw-review">{review.map((item) => {
        const comparison = item.payload?.comparison;
        return <li key={item.id}>
          <strong>{item.status.replaceAll('_',' ')} · {item.receipt_label}</strong>
          <p>Source locator: {display(item.locator || comparison?.current_locator)}. Prior locator: {display(comparison?.previous_locator)}.</p>
          <p>{item.payload?.meaning ?? item.payload?.assertion ?? 'Source evidence retained for review.'}</p>
          {item.payload?.source_row?.problems?.length ? <p>Quarantine: {item.payload.source_row.problems.join('; ')}</p> : null}
          {comparison?.fields?.length ? <table><thead><tr><th scope="col">Field</th><th scope="col">Prior accepted</th><th scope="col">This delivery</th></tr></thead><tbody>
            {comparison.fields.map((field,index) => <tr key={`${field.field}-${index}`}><th scope="row">{field.field.replaceAll('_',' ')}</th><td>{display(field.old)}</td><td>{display(field.new)}</td></tr>)}
          </tbody></table> : null}
          <p className="iw-muted">Receipt {item.receipt_id}{comparison?.previous_receipt_id ? ` · baseline receipt ${comparison.previous_receipt_id}` : ''}. Full receipt/attempt payloads are shared source context; this case remains scoped to the network and location above.</p>
        </li>;
      })}</ol>
    </details>}
  </section>;
}
