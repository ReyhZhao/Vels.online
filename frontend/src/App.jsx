import { Routes, Route } from 'react-router-dom';
import PublicLayout from './components/layout/PublicLayout';
import AdminLayout from './components/layout/AdminLayout';
import SecurityLayout from './components/layout/SecurityLayout';
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

      <Route
        path="/admin"
        element={<ProtectedRoute><AdminLayout /></ProtectedRoute>}
      >
        <Route index element={<AdminDashboard />} />
        <Route path="posts" element={<AdminPostList />} />
        <Route path="posts/new" element={<AdminPostForm />} />
        <Route path="posts/:slug/edit" element={<AdminPostForm />} />
        <Route path="status-settings" element={<StatusSettings />} />
        <Route path="security/organizations" element={<OrgManagement />} />
        <Route path="security/downloads" element={<DownloadManagement />} />
      </Route>

      <Route
        path="/security"
        element={<ProtectedRoute><SecurityLayout /></ProtectedRoute>}
      >
        <Route index element={<SecurityDashboard />} />
        <Route path="vulnerabilities" element={<VulnerabilityDashboard />} />
        <Route path="vulnerabilities/:cveId" element={<CveDetail />} />
        <Route path="enroll" element={<EnrollmentPage />} />
        <Route path="agents/:agentId" element={<AgentDetail />} />
      </Route>
    </Routes>
  );
}

export default App;
