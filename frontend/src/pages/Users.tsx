import { useEffect, useState } from "react";
import { api, AuthUser, ROLES } from "../api";
import { ErrorBox, hasRole, useAuth, when } from "../components/common";

export default function Users() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AuthUser[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const load = () => api.users().then(setUsers).catch(setError);
  useEffect(() => { if (hasRole(me, "admin")) load(); }, [me]);

  if (!hasRole(me, "admin")) return <div className="empty">Admins only.</div>;

  async function toggleRole(u: AuthUser, role: string) {
    const roles = u.roles.includes(role) ? u.roles.filter((r) => r !== role) : [...u.roles, role];
    try {
      await api.updateUser(u.id, { roles });
      load();
    } catch (e) {
      setError(e);
    }
  }

  async function toggleActive(u: AuthUser) {
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      load();
    } catch (e) {
      setError(e);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Users &amp; roles</h1>
          <div className="sub">
            Registration is self-service into a plain member — anyone can join and rate/submit work. Elevated
            roles (below) are granted here. A role only adds to what a member can already do; separation-of-duties
            checks (e.g. no self-approval) always apply regardless of role.
          </div>
        </div>
      </div>
      <ErrorBox error={error} />
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        {!users ? <div className="empty">Loading…</div> : (
          <table>
            <thead>
              <tr>
                <th>User</th>
                {ROLES.map((r) => <th key={r} className="num">{r}</th>)}
                <th>Last login</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td><b>{u.display_name}</b> <span className="muted small">@{u.username}</span></td>
                  {ROLES.map((r) => (
                    <td key={r} className="num">
                      <input type="checkbox" checked={u.roles.includes(r)} onChange={() => toggleRole(u, r)} />
                    </td>
                  ))}
                  <td className="small muted">{when(u.last_login_at)}</td>
                  <td>
                    <button className="sm" disabled={u.id === me?.id && u.is_active} title={u.id === me?.id ? "You cannot deactivate your own account" : ""}
                           onClick={() => toggleActive(u)}>
                      {u.is_active ? "Active" : "Deactivated"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
