import { Routes, Route } from 'react-router-dom';
import PublicLayout from './components/layout/PublicLayout';
import AppLayout from './components/layout/AppLayout';
import LandingPage from './pages/LandingPage';
import BlogIndexPage from './pages/BlogIndexPage';
import PostDetail from './pages/PostDetail';
import StatusPage from './pages/StatusPage';
import AdminDashboard from './pages/admin/AdminDashboard';
import AdminPostList from './pages/AdminPostList';
import AdminPostForm from './pages/AdminPostForm';
import StatusSettings from './pages/admin/StatusSettings';
import OrgManagement from './pages/admin/OrgManagement';
import DownloadManagement from './pages/admin/DownloadManagement';
import SecurityDashboard from './pages/SecurityDashboard';
import VulnerabilityDashboard from './pages/VulnerabilityDashboard';
import CveDetail from './pages/CveDetail';
import EnrollmentPage from './pages/EnrollmentPage';
import AgentDetail from './pages/AgentDetail';
import FleetEventsPage from './pages/FleetEventsPage';
import DashboardPage from './pages/DashboardPage';
import WorkPackagePage from './pages/WorkPackagePage';
import RiskAcceptancePage from './pages/RiskAcceptancePage';
import IncidentList from './pages/IncidentList';
import IncidentDetail from './pages/IncidentDetail';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/blog" element={<BlogIndexPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/:slug" element={<PostDetail />} />
      </Route>

      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/posts" element={<AdminPostList />} />
        <Route path="/admin/posts/new" element={<AdminPostForm />} />
        <Route path="/admin/posts/:slug/edit" element={<AdminPostForm />} />
        <Route path="/admin/status-settings" element={<StatusSettings />} />
        <Route path="/admin/security/organizations" element={<OrgManagement />} />
        <Route path="/admin/security/downloads" element={<DownloadManagement />} />

        <Route path="/security" element={<SecurityDashboard />} />
        <Route path="/security/vulnerabilities" element={<VulnerabilityDashboard />} />
        <Route path="/security/vulnerabilities/:cveId" element={<CveDetail />} />
        <Route path="/security/events" element={<FleetEventsPage />} />
        <Route path="/security/enroll" element={<EnrollmentPage />} />
        <Route path="/security/agents/:agentId" element={<AgentDetail />} />
        <Route path="/security/work-package" element={<WorkPackagePage />} />
        <Route path="/security/risk-acceptances" element={<RiskAcceptancePage />} />

        <Route path="/incidents" element={<IncidentList />} />
        <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
      </Route>
    </Routes>
  );
}

export default App;
