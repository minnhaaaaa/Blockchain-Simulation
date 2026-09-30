import { Navigate, Route, Routes } from "react-router-dom";
import { useApi } from "./api/ApiContext";
import { LandingPage } from "./pages/LandingPage";
import { SignInPage } from "./pages/SignInPage";
import { AppShell, RoomGuard } from "./components/AppShell";
import { GatewayPage } from "./pages/GatewayPage";
import { OverviewPage } from "./pages/OverviewPage";
import { JobsPage } from "./pages/JobsPage";
import { NewJobPage } from "./pages/NewJobPage";
import { JobDetailPage } from "./pages/JobDetailPage";
import { NetworkPage } from "./pages/NetworkPage";
import { LedgerPage } from "./pages/LedgerPage";
import { SecurityPage } from "./pages/SecurityPage";
import { SettingsPage } from "./pages/SettingsPage";

function AuthGuard({ children }: { children: React.ReactNode }) { const {client}=useApi(); return client ? children : <Navigate to="/sign-in" replace/>; }
function ConsoleRoute({ children }: { children: React.ReactNode }) { return <AuthGuard><AppShell><RoomGuard>{children}</RoomGuard></AppShell></AuthGuard>; }

export default function App() {
  return <Routes>
    <Route path="/" element={<LandingPage />} />
    <Route path="/sign-in" element={<SignInPage />} />
    <Route path="/connect" element={<AuthGuard><GatewayPage /></AuthGuard>} />
    <Route path="/r/:roomId/overview" element={<ConsoleRoute><OverviewPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/jobs" element={<ConsoleRoute><JobsPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/jobs/new" element={<ConsoleRoute><NewJobPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/jobs/:jobId" element={<ConsoleRoute><JobDetailPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/network" element={<ConsoleRoute><NetworkPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/ledger" element={<ConsoleRoute><LedgerPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/security" element={<ConsoleRoute><SecurityPage /></ConsoleRoute>} />
    <Route path="/r/:roomId/settings" element={<ConsoleRoute><SettingsPage /></ConsoleRoute>} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes>;
}
