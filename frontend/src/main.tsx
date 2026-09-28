import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import "./styles.css";
import { restoreSession } from "./api";
import Library from "./pages/Library";
import Builder from "./pages/Builder";
import NewEvaluation from "./pages/NewEvaluation";
import EvaluationPage from "./pages/EvaluationPage";
import Evaluations from "./pages/Evaluations";
import Analytics from "./pages/Analytics";
import ImportPage from "./pages/Import";
import Work from "./pages/Work";
import SubjectPage from "./pages/SubjectPage";
import SubmissionPage from "./pages/SubmissionPage";
import Attention from "./pages/Attention";
import Login from "./pages/Login";
import Users from "./pages/Users";
import { hasRole, LoggedInAs, useAuth } from "./components/common";

function Shell() {
  const { user } = useAuth();
  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">
          Scorecard Studio
          <small>Create · Rate · Improve</small>
        </div>
        <LoggedInAs />
        <div className="section">Design</div>
        <NavLink to="/" end>Scorecard library</NavLink>
        <NavLink to="/import">Import legacy</NavLink>
        <div className="section">Work</div>
        <NavLink to="/work">Work &amp; gates</NavLink>
        <NavLink to="/attention">Needs attention</NavLink>
        <div className="section">Rate</div>
        <NavLink to="/evaluate">Quick evaluation</NavLink>
        <NavLink to="/evaluations">Evaluations</NavLink>
        <div className="section">Learn</div>
        <NavLink to="/analytics">Analytics</NavLink>
        {hasRole(user, "admin") && (
          <>
            <div className="section">Admin</div>
            <NavLink to="/users">Users &amp; roles</NavLink>
          </>
        )}
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/versions/:versionId" element={<Builder />} />
          <Route path="/evaluate" element={<NewEvaluation />} />
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/evaluations/:evaluationId" element={<EvaluationPage />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/work" element={<Work />} />
          <Route path="/subjects/:subjectId" element={<SubjectPage />} />
          <Route path="/submissions/:submissionId" element={<SubmissionPage />} />
          <Route path="/attention" element={<Attention />} />
          <Route path="/users" element={<Users />} />
          <Route path="*" element={<div className="empty">Page not found</div>} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  const { user } = useAuth();
  const [checking, setChecking] = useState(true);
  useEffect(() => { restoreSession().finally(() => setChecking(false)); }, []);
  if (checking) return <div className="empty">Loading…</div>;
  return user ? <Shell /> : <Login />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
