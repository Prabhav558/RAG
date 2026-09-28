import { useState } from "react";
import { login, register } from "../api";
import { ErrorBox, Field } from "../components/common";

export default function Login() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(username.trim(), password);
      else await register({ username: username.trim(), password, display_name: displayName.trim(), email: email.trim() || undefined });
      // On success, api.ts's auth-changed event flips the app into the logged-in shell — nothing else to do here.
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-screen">
      <div className="card login-card">
        <h1>Scorecard Studio</h1>
        <div className="sub">Create · Rate · Improve</div>
        <div className="tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(null); }}>Log in</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(null); }}>Register</button>
        </div>
        <ErrorBox error={error} />
        <form
          onSubmit={(e) => { e.preventDefault(); submit(); }}
        >
          <Field label="Username">
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus autoComplete="username" />
          </Field>
          {mode === "register" && (
            <Field label="Display name" hint="Shown on everything you do: submissions, ratings, diagnoses.">
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} autoComplete="name" />
            </Field>
          )}
          <Field label="Password" hint={mode === "register" ? "At least 8 characters." : undefined}>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </Field>
          {mode === "register" && (
            <Field label="Email (optional)">
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
            </Field>
          )}
          <button type="submit" className="primary" style={{ width: "100%", marginTop: 8 }}
                 disabled={busy || !username.trim() || !password || (mode === "register" && !displayName.trim())}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
        {mode === "register" && (
          <p className="hint" style={{ marginTop: 10 }}>
            The very first account ever created on a fresh database becomes an admin automatically. Everyone
            else starts as a plain member; an admin grants roles afterwards (Admin → Users).
          </p>
        )}
      </div>
    </div>
  );
}
