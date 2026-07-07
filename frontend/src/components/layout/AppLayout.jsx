import { useCallback, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { OrgProvider } from '../../context/OrgContext';
import { useSwipeGesture } from '../../hooks/useSwipeGesture';
import AppSidebar from './AppSidebar';
import TopNav from './TopNav';
import Breadcrumb from './Breadcrumb';

function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const contentRef = useRef(null);

  useSwipeGesture(contentRef, useCallback(() => setMobileOpen(true), []));

  return (
    <OrgProvider>
      <div className="flex h-screen flex-col">
        <TopNav onMenuClick={() => setMobileOpen((o) => !o)} />
        <div className="flex flex-1 overflow-hidden" ref={contentRef}>
          <AppSidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
          <div className="flex flex-1 flex-col bg-background overflow-auto thin-scrollbar">
            <Breadcrumb />
            <Outlet />
          </div>
        </div>
      </div>
    </OrgProvider>
  );
}

export default AppLayout;
