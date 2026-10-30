import { useEffect, useState } from 'react';
import './network-setup.css';

type Organization = {id:string;label:string;kind:string;identifiers?:unknown;actor:string;reason:string;created_at:string};
type Network = {id:string;label:string;payer_organization_id:string|null;actor:string;reason:string;created_at:string};
type Location = {id:string;label:string;organization_id:string|null;actor:string;reason:string;created_at:string};
export type BindingKind = 'network' | 'organization' | 'location';
export type Binding = {id:string;source:string;kind:BindingKind;source_key:string;target_id:string;previous_id:string|null;revision:number;actor:string;reason:string;created_at:string;current:boolean};
export type Catalog = {organizations:Organization[];networks:Network[];locations:Location[];bindings:Binding[]};
export type RosterBindings = Record<BindingKind,Record<string,string>>;
export const emptyRosterBindings = ():RosterBindings => ({network:{},organization:{},location:{}});
const emptyCatalog:Catalog = {organizations:[],networks:[],locations:[],bindings:[]};
const kinds:BindingKind[] = ['network','organization','location'];
const showTarget = (catalog:Catalog, binding:Binding) => {
  const list = binding.kind === 'network' ? catalog.networks : binding.kind === 'location' ? catalog.locations : catalog.organizations;
  return list.find((item) => item.id === binding.target_id)?.label ?? binding.target_id;
};
async function api(path:string, body?:unknown) {
  const response = await fetch(`/api${path}`, body === undefined ? undefined : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (!response.ok) {
    const detail = await response.json().catch(() => ({})) as {detail?:unknown};
    throw new Error(typeof detail.detail === 'string' ? detail.detail : `Catalog request failed (${response.status})`);
  }
  return response.json();
}
function useCatalog() {
  const [catalog,setCatalog] = useState<Catalog>(emptyCatalog);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const refresh = async () => {
    setLoading(true);setError('');
    try {
      const data = await api('/catalog') as Catalog;
      setCatalog({organizations:data.organizations ?? [],networks:data.networks ?? [],locations:data.locations ?? [],bindings:data.bindings ?? []});
    } catch (e) {setError((e as Error).message);} finally {setLoading(false);}
  };
  useEffect(() => {void refresh();}, []);
  return {catalog,loading,error,refresh};
}

export function NetworkSetup({source}: {source:string}) {
  const {catalog,loading,error:loadError,refresh} = useCatalog();
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [actor,setActor] = useState('');
  const [reason,setReason] = useState('');
  const [organization,setOrganization] = useState({label:'',kind:'clinic'});
  const [network,setNetwork] = useState({label:'',payer_organization_id:''});
  const [location,setLocation] = useState({label:'',organization_id:''});
  const [binding,setBinding] = useState({source,kind:'network' as BindingKind,source_key:'',target_id:''});
  useEffect(() => {setBinding((old) => ({...old,source}));},[source]);
  const current = catalog.bindings.find((item) => item.current && item.source === binding.source && item.kind === binding.kind && item.source_key === binding.source_key.trim());
  const targets = binding.kind === 'network' ? catalog.networks : binding.kind === 'location' ? catalog.locations : catalog.organizations;
  const save = async (path:string,payload:Record<string,unknown>,clear:() => void) => {
    setBusy(true);setError('');
    try {await api(path,{...payload,actor,reason});clear();await refresh();}
    catch (e) {setError((e as Error).message);}
    finally {setBusy(false);}
  };
  return <details className="ns-setup iw-card">
    <summary><strong>Organization and network setup</strong> · Create explicit records and reviewed source bindings</summary>
    <p className="iw-muted">Set up a payer, its networks, a clinic and locations, then bind exact source codes to those records. Creating records or bindings does not import, accept, verify or merge provider data. Equal labels may have different IDs.</p>
    {loading && <p role="status">Loading catalog…</p>}
    {(error || loadError) && <p className="iw-error" role="alert">{error || loadError}</p>}
    <button type="button" onClick={() => void refresh()} disabled={busy}>Refresh catalog</button>
    <div className="ns-reviewer iw-form">
      <label>Catalog reviewer<input disabled={busy} value={actor} onChange={(event) => setActor(event.target.value)} required /></label>
      <label>Catalog reason<input disabled={busy} value={reason} onChange={(event) => setReason(event.target.value)} required /></label>
    </div>
    <div className="ns-grid">
      <form onSubmit={(event) => {event.preventDefault();void save('/catalog/organizations',organization,() => setOrganization({...organization,label:''}));}}>
        <fieldset disabled={busy} className="ns-form-fields">
        <h3>1. Organization</h3>
        <label>Organization label<input required value={organization.label} onChange={(event) => setOrganization({...organization,label:event.target.value})} /></label>
        <label>Organization kind<select value={organization.kind} onChange={(event) => setOrganization({...organization,kind:event.target.value})}>
          {['payer','clinic','group','health_system','other'].map((kind) => <option key={kind} value={kind}>{kind.replaceAll('_',' ')}</option>)}
        </select></label>
        <button disabled={busy || !actor || !reason}>Create organization</button>
        </fieldset>
      </form>
      <form onSubmit={(event) => {event.preventDefault();void save('/catalog/networks',{label:network.label,payer_organization_id:network.payer_organization_id || null},() => setNetwork({...network,label:''}));}}>
        <fieldset disabled={busy} className="ns-form-fields">
        <h3>2. Payer network</h3>
        <label>Network label<input required value={network.label} onChange={(event) => setNetwork({...network,label:event.target.value})} /></label>
        <label>Payer organization<select value={network.payer_organization_id} onChange={(event) => setNetwork({...network,payer_organization_id:event.target.value})}>
          <option value="">Unknown</option>{catalog.organizations.filter((item) => item.kind === 'payer').map((item) => <option key={item.id} value={item.id}>{item.label} · {item.id}</option>)}
        </select></label>
        <button disabled={busy || !actor || !reason}>Create network</button>
        </fieldset>
      </form>
      <form onSubmit={(event) => {event.preventDefault();void save('/catalog/locations',{label:location.label,organization_id:location.organization_id || null},() => setLocation({...location,label:''}));}}>
        <fieldset disabled={busy} className="ns-form-fields">
        <h3>3. Practice location</h3>
        <label>Location label<input required value={location.label} onChange={(event) => setLocation({...location,label:event.target.value})} /></label>
        <label>Clinic organization<select value={location.organization_id} onChange={(event) => setLocation({...location,organization_id:event.target.value})}>
          <option value="">Unknown</option>{catalog.organizations.filter((item) => item.kind !== 'payer').map((item) => <option key={item.id} value={item.id}>{item.label} · {item.id}</option>)}
        </select></label>
        <button disabled={busy || !actor || !reason}>Create location</button>
        </fieldset>
      </form>
    </div>
    <form className="ns-binding" onSubmit={(event) => {event.preventDefault();void save('/catalog/bindings',{
      source:binding.source,kind:binding.kind,source_key:binding.source_key.trim(),target_id:binding.target_id,
      expected_binding_id:current?.id ?? null,
    },() => setBinding({...binding,source_key:'',target_id:''}));}}>
      <fieldset disabled={busy} className="ns-form-fields">
      <h3>4. Review a source-code binding</h3>
      <p className="iw-muted">Source codes are exact. Replacing an existing binding requires its current revision; a stale edit is rejected by the service.</p>
      <div className="iw-form">
        <label>Binding source<input required disabled={busy} value={binding.source} onChange={(event) => setBinding({...binding,source:event.target.value})} /></label>
        <label>Binding kind<select disabled={busy} value={binding.kind} onChange={(event) => setBinding({...binding,kind:event.target.value as BindingKind,target_id:''})}>
          {kinds.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
        </select></label>
        <label>Exact source code<input required disabled={busy} value={binding.source_key} onChange={(event) => setBinding({...binding,source_key:event.target.value})} /></label>
        <label>Reviewed target<select required disabled={busy} value={binding.target_id} onChange={(event) => setBinding({...binding,target_id:event.target.value})}>
          <option value="">Choose catalog record</option>{targets.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.id}</option>)}
        </select></label>
      </div>
      {current && <p className="iw-notice">Current binding revision {current.revision}: {showTarget(catalog,current)} · {current.id}. Saving replaces this exact revision; history remains.</p>}
      <button disabled={busy || !actor || !reason || !binding.source || !binding.source_key.trim() || !binding.target_id}>Save reviewed binding</button>
      </fieldset>
    </form>
    <h3>Current source bindings</h3>
    <ul className="ns-list">{catalog.bindings.filter((item) => item.current && item.source === source).map((item) => <li key={item.id}>{item.kind} <strong>{item.source_key}</strong> → {showTarget(catalog,item)} · revision {item.revision} · {item.id}</li>)}</ul>
  </details>;
}

export function RosterConfiguration({source,kind,bindings,fixedNetworkBindingId,busy,onKind,onBindings,onFixedNetworkBindingId}: {
  source:string;
  kind:'clinic'|'network';
  bindings:RosterBindings;
  fixedNetworkBindingId:string;
  busy:boolean;
  onKind:(kind:'clinic'|'network')=>void;
  onBindings:(bindings:RosterBindings)=>void;
  onFixedNetworkBindingId:(id:string)=>void;
}) {
  const {catalog,error,refresh} = useCatalog();
  const sourceBindings = catalog.bindings.filter((item) => item.current && item.source === source);
  const staleSelections = kinds.flatMap((bindingKind) => Object.entries(bindings[bindingKind] ?? {})
    .filter(([sourceKey,id]) => !sourceBindings.some((item) => item.kind === bindingKind && item.source_key === sourceKey && item.id === id))
    .map(([sourceKey,id]) => ({bindingKind,sourceKey,id})));
  const selected = (item:Binding) => bindings[item.kind]?.[item.source_key] === item.id;
  const toggle = (item:Binding) => {
    const next = {...bindings,[item.kind]:{...bindings[item.kind]}};
    if (selected(item)) delete next[item.kind][item.source_key];
    else next[item.kind][item.source_key] = item.id;
    onBindings(next);
  };
  return <section className="ns-roster" aria-label="Roster configuration">
    <h4>Roster interpretation</h4>
    <label>Roster kind<select value={kind} onChange={(event) => onKind(event.target.value as 'clinic'|'network')} disabled={busy}>
      <option value="clinic">Clinic directory (default)</option><option value="network">Payer-network participation</option>
    </select></label>
    {kind === 'network' && <>
      <p className="iw-muted">Select only reviewed bindings used by this delivery. Labels and NPI do not establish membership or location identity. Source-listed status and dates remain source claims, separate from human verification.</p>
      {error && <p className="iw-error" role="alert">{error}</p>}
      <button type="button" onClick={() => void refresh()} disabled={busy}>Refresh reviewed bindings</button>
      {staleSelections.length > 0 && <div className="iw-notice">
        <strong>Selected binding revisions are no longer current.</strong>
        <p>Review and select current revisions before reprocessing; the service rejects stale bindings at acceptance.</p>
        <ul>{staleSelections.map((item) => <li key={`${item.bindingKind}-${item.sourceKey}`}>{item.bindingKind} {item.sourceKey} · {item.id}</li>)}</ul>
        <button type="button" disabled={busy} onClick={() => {
          const next: RosterBindings = {network:{...bindings.network},organization:{...bindings.organization},location:{...bindings.location}};
          for (const item of staleSelections) delete next[item.bindingKind][item.sourceKey];
          onBindings(next);
        }}>Clear stale selections</button>
      </div>}
      {kinds.map((bindingKind) => <fieldset key={bindingKind}>
        <legend>{bindingKind} source codes</legend>
        {sourceBindings.filter((item) => item.kind === bindingKind).length === 0 && <p className="iw-muted">No reviewed {bindingKind} bindings for {source}.</p>}
        {sourceBindings.filter((item) => item.kind === bindingKind).map((item) => <label className="ns-checkbox" key={item.id}>
          <input type="checkbox" checked={selected(item)} onChange={() => toggle(item)} disabled={busy} />
          {item.source_key} → {showTarget(catalog,item)} · revision {item.revision}
        </label>)}
      </fieldset>)}
      <label>Fixed single-network binding (optional, explicit)<select value={fixedNetworkBindingId} onChange={(event) => onFixedNetworkBindingId(event.target.value)} disabled={busy}>
        <option value="">Use row network codes</option>
        {sourceBindings.filter((item) => item.kind === 'network' && selected(item)).map((item) => <option key={item.id} value={item.id}>{item.source_key} → {showTarget(catalog,item)}</option>)}
      </select></label>
      <p className="iw-muted">A fixed network applies only when explicitly selected. Conflicting row codes are quarantined. Save mapping and reprocess, inspect validation and comparison, then accept separately.</p>
    </>}
  </section>;
}
