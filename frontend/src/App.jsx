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
import SecurityDashboard from './pages/SecurityDashboard';
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
      </Route>

      <Route
        path="/security"
        element={<ProtectedRoute><SecurityLayout /></ProtectedRoute>}
      >
        <Route index element={<SecurityDashboard />} />
      </Route>
    </Routes>
  );
}

export default App;
