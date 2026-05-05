import { useCallback, useRef, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Menu } from 'lucide-react';
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
      <div className="flex min-h-screen flex-col">
        <TopNav />
        <div className="flex h-12 items-center border-b border-border px-4 md:hidden">
          <button
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Toggle menu"
            className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <Menu className="h-5 w-5" />
          </button>
        </div>
        <div className="flex flex-1 overflow-hidden" ref={contentRef}>
          <AppSidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
          <div className="flex flex-1 flex-col bg-background overflow-auto">
            <Breadcrumb />
            <Outlet />
          </div>
        </div>
      </div>
    </OrgProvider>
  );
}

export default AppLayout;
