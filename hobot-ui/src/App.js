import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import RegisterPage from './components/RegisterPage';
import Dashboard from './components/Dashboard';
import MainPage from './components/MainPage';
import './App.css';

// Protected Route 컴포넌트
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>로딩 중...</div>;
  }

  return user ? children : <Navigate to="/" replace />;
};

// Admin Protected Route 컴포넌트 (향후 사용 예정)
// eslint-disable-next-line no-unused-vars
const AdminRoute = ({ children }) => {
  const { user, loading, isAdmin } = useAuth();

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>로딩 중...</div>;
  }

  if (!user) {
    return <Navigate to="/" replace />;
  }

  if (!isAdmin()) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

function AppRoutes() {
  const { user } = useAuth();

  return (
    <Routes>
      <Route 
        path="/register" 
        element={
          user ? 
            <Navigate to="/dashboard" replace /> : 
            <RegisterPage />
        } 
      />
      <Route 
        path="/dashboard" 
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } 
      />
      <Route 
        path="/" 
        element={<MainPage />} 
      />
    </Routes>
  );
}

function App() {
  return (
    <AuthProvider>
      <Router>
        <div className="App">
          <AppRoutes />
        </div>
      </Router>
    </AuthProvider>
  );
}

export default App;
