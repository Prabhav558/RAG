import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import "./styles.css";
import Library from "./pages/Library";
import Builder from "./pages/Builder";
import NewEvaluation from "./pages/NewEvaluation";
import EvaluationPage from "./pages/EvaluationPage";
import Evaluations from "./pages/Evaluations";
import Analytics from "./pages/Analytics";

function App() {
  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">
          Scorecard Studio
          <small>Create · Rate · Improve</small>
        </div>
        <NavLink to="/" end>Scorecard library</NavLink>
        <NavLink to="/evaluate">New evaluation</NavLink>
        <NavLink to="/evaluations">Evaluations</NavLink>
        <NavLink to="/analytics">Analytics</NavLink>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/versions/:versionId" element={<Builder />} />
          <Route path="/evaluate" element={<NewEvaluation />} />
          <Route path="/evaluations" element={<Evaluations />} />
          <Route path="/evaluations/:evaluationId" element={<EvaluationPage />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="*" element={<div className="empty">Page not found</div>} />
        </Routes>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
