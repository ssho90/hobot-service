import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { Header } from './components/Header';

const RegisterPage = lazy(() => import('./components/RegisterPage'));
const Dashboard = lazy(() => import('./components/Dashboard'));
const AboutPage = lazy(() => import('./components/AboutPage').then((module) => ({ default: module.AboutPage })));
const TradingDashboard = lazy(() => import('./components/TradingDashboard'));
const AdminUserManagement = lazy(() => import('./components/admin/AdminUserManagement').then((module) => ({ default: module.AdminUserManagement })));
const AdminLogManagement = lazy(() => import('./components/admin/AdminLogManagement').then((module) => ({ default: module.AdminLogManagement })));
const AdminLLMMonitoring = lazy(() => import('./components/admin/AdminLLMMonitoring').then((module) => ({ default: module.AdminLLMMonitoring })));
const AdminRebalancing = lazy(() => import('./components/admin/AdminRebalancing').then((module) => ({ default: module.AdminRebalancing })));
const AdminFileUpload = lazy(() => import('./components/admin/AdminFileUpload').then((module) => ({ default: module.AdminFileUpload })));
const OntologyPage = lazy(() => import('./components/OntologyPage'));

const PageLoader: React.FC = () => (
  <div className="flex flex-1 items-center justify-center py-16">
    <div className="h-8 w-8 border-4 border-zinc-200 border-t-blue-500 rounded-full animate-spin" />
  </div>
);

// Main App Component
const AppLayout: React.FC = () => {
  const location = useLocation();

  // Don't show header on register page
  const showHeader = !['/register'].includes(location.pathname);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {showHeader && <Header />}
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/trading" element={<TradingDashboard />} />
          <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
          <Route path="/admin/users" element={<AdminUserManagement />} />
          <Route path="/admin/logs" element={<AdminLogManagement />} />
          <Route path="/admin/llm" element={<AdminLLMMonitoring />} />
          <Route path="/admin/rebalancing" element={<AdminRebalancing />} />
          <Route path="/admin/files" element={<AdminFileUpload />} />
          <Route path="/ontology/architecture" element={<OntologyPage mode="architecture" />} />
          <Route path="/ontology/news" element={<OntologyPage mode="news" />} />
          <Route path="/ontology" element={<Navigate to="/ontology/architecture" replace />} />
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </Suspense>
    </div>
  );
};


// Main App Component
function App() {
  return (
    <AuthProvider>
      <Router>
        <AppLayout />
      </Router>
    </AuthProvider>
  );
}

export default App;
