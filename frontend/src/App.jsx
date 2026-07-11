import { lazy, Suspense } from 'react';
import { Routes, Route, Outlet } from 'react-router-dom';
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
import ServiceAccountsAdmin from './pages/admin/ServiceAccountsAdmin';
import DownloadManagement from './pages/admin/DownloadManagement';
import SubjectsAdmin from './pages/admin/SubjectsAdmin';
import TaskTemplatesAdmin from './pages/admin/TaskTemplatesAdmin';
import ReportTemplatesAdmin from './pages/admin/ReportTemplatesAdmin';
import TriageLessonsReview from './pages/admin/TriageLessonsReview';
import AutomationsAdmin from './pages/admin/AutomationsAdmin';
import WazuhResponsesAdmin from './pages/admin/WazuhResponsesAdmin';
import PartnerConnections from './pages/admin/PartnerConnections';
import IntakeInbox from './pages/admin/IntakeInbox';
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
import ReportsPage from './pages/ReportsPage';
import IncidentDetail from './pages/IncidentDetail';
import AlertsPage from './pages/AlertsPage';
import ExceptionList from './pages/ExceptionList';
import RouteList from './pages/RouteList';
import RouteDetail from './pages/RouteDetail';
import NotificationPreferences from './pages/account/NotificationPreferences';
import SignupPage from './pages/SignupPage';
import SignupRequests from './pages/admin/SignupRequests';
import TaskHistory from './pages/admin/TaskHistory';
import ScheduledTasks from './pages/admin/ScheduledTasks';
import EmailTemplates from './pages/admin/EmailTemplates';
import TaskListPage from './pages/TaskListPage';
import ContactsPage from './pages/ContactsPage';
import ContactDetail from './pages/ContactDetail';
import AssetsPage from './pages/AssetsPage';
import AssetDetail from './pages/AssetDetail';
import OnCallCalendarPage from './pages/admin/OnCallCalendarPage';
import CorrelationRulesAdmin from './pages/admin/CorrelationRulesAdmin';
import SearchRulesAdmin from './pages/admin/SearchRulesAdmin';
import ThreatHuntingPage from './pages/ThreatHuntingPage';
import HuntDetail from './pages/HuntDetail';
// Lazy so the heavy map deps (d3-geo, topojson-client, world-atlas) code-split out of
// the main bundle until a staff user opens the map (also keeps the bundle under the
// PWA precache size limit).
const LiveAttackMap = lazy(() => import('./pages/LiveAttackMap'));
import ProtectedRoute from './components/ProtectedRoute';
import StaffOnlyRoute from './components/StaffOnlyRoute';

function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route path="/" element={<LandingPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/blog" element={<BlogIndexPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/:slug" element={<PostDetail />} />
      </Route>

      <Route element={<ProtectedRoute><AppLayout /></ProtectedRoute>}>
        <Route path="/dashboard" element={<DashboardPage />} />

        <Route element={<StaffOnlyRoute><Outlet /></StaffOnlyRoute>}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/posts" element={<AdminPostList />} />
          <Route path="/admin/posts/new" element={<AdminPostForm />} />
          <Route path="/admin/posts/:slug/edit" element={<AdminPostForm />} />
          <Route path="/admin/status-settings" element={<StatusSettings />} />
          <Route path="/admin/security/organizations" element={<OrgManagement />} />
          <Route path="/admin/security/service-accounts" element={<ServiceAccountsAdmin />} />
          <Route path="/admin/security/downloads" element={<DownloadManagement />} />
          <Route path="/admin/signup-requests" element={<SignupRequests />} />
          <Route path="/admin/incidents/subjects" element={<SubjectsAdmin />} />
          <Route path="/admin/incidents/task-templates" element={<TaskTemplatesAdmin />} />
          <Route path="/admin/incidents/report-templates" element={<ReportTemplatesAdmin />} />
          <Route path="/admin/incidents/triage-lessons" element={<TriageLessonsReview />} />
          <Route path="/admin/incidents/automations" element={<AutomationsAdmin />} />
          <Route path="/admin/wazuh-responses" element={<WazuhResponsesAdmin />} />
          <Route path="/admin/partners/connections" element={<PartnerConnections />} />
          <Route path="/admin/partners/intake-inbox" element={<IntakeInbox />} />
          <Route path="/admin/incidents/oncall" element={<OnCallCalendarPage />} />
          <Route path="/admin/correlations/rules" element={<CorrelationRulesAdmin />} />
          <Route path="/admin/correlations/search-rules" element={<SearchRulesAdmin />} />
          <Route path="/hunting" element={<ThreatHuntingPage />} />
          <Route path="/hunting/:huntId" element={<HuntDetail />} />
          <Route path="/admin/tasks/history" element={<TaskHistory />} />
          <Route path="/admin/tasks/scheduled" element={<ScheduledTasks />} />
          <Route path="/admin/email-templates" element={<EmailTemplates />} />
          <Route
            path="/attack-map"
            element={
              <Suspense fallback={<div className="flex h-full items-center justify-center text-sm text-muted-foreground">Loading attack map…</div>}>
                <LiveAttackMap />
              </Suspense>
            }
          />
        </Route>

        <Route path="/security" element={<SecurityDashboard />} />
        <Route path="/security/vulnerabilities" element={<VulnerabilityDashboard />} />
        <Route path="/security/vulnerabilities/:cveId" element={<CveDetail />} />
        <Route path="/security/events" element={<FleetEventsPage />} />
        <Route path="/security/enroll" element={<EnrollmentPage />} />
        <Route path="/security/agents/:agentId" element={<AgentDetail />} />
        <Route path="/security/work-package" element={<WorkPackagePage />} />
        <Route path="/security/risk-acceptances" element={<RiskAcceptancePage />} />

        <Route path="/incidents" element={<IncidentList />} />
        <Route path="/incidents/:displayId" element={<IncidentDetail />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/tasks" element={<TaskListPage />} />
        <Route path="/exceptions" element={<ExceptionList />} />
        <Route path="/routes" element={<RouteList />} />
        <Route path="/routes/:fqdn" element={<RouteDetail />} />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/contacts/:id" element={<ContactDetail />} />
        <Route path="/assets" element={<AssetsPage />} />
        <Route path="/assets/:id" element={<AssetDetail />} />

        <Route path="/account/notifications" element={<NotificationPreferences />} />
      </Route>
    </Routes>
  );
}

export default App;
