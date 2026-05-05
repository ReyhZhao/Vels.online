import { Outlet } from 'react-router-dom';
import { OrgProvider } from '../../context/OrgContext';
import AppSidebar from './AppSidebar';
import TopNav from './TopNav';
import Breadcrumb from './Breadcrumb';

function AppLayout() {
  return (
    <OrgProvider>
      <div className="flex min-h-screen flex-col">
        <TopNav />
        <div className="flex flex-1">
          <AppSidebar />
          <div className="flex flex-1 flex-col bg-background">
            <Breadcrumb />
            <Outlet />
          </div>
        </div>
      </div>
    </OrgProvider>
  );
}

export default AppLayout;
