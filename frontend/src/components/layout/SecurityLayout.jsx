import { Outlet } from 'react-router-dom';
import { OrgProvider } from '../../context/OrgContext';
import OrgSwitcher from '../OrgSwitcher';

function SecurityLayout() {
  return (
    <OrgProvider>
      <div className="flex min-h-screen flex-col bg-background">
        <header className="flex h-14 items-center justify-between border-b border-border px-6">
          <span className="text-sm font-semibold text-foreground">Security</span>
          <OrgSwitcher />
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </OrgProvider>
  );
}

export default SecurityLayout;
