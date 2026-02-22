import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, TrendingUp, Bell, ChevronDown } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { LoginModal } from './LoginModal';

export const Header: React.FC = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isAdminOpen, setIsAdminOpen] = useState(false); // Mobile toggle
  const [isOntologyOpen, setIsOntologyOpen] = useState(false); // Mobile toggle
  const location = useLocation();
  const { user, isAuthenticated, logout } = useAuth();
  const isAdmin = user?.role === 'admin';
  const isArchitect = user?.role === 'architect' || isAdmin;

  const navItems = [
    { path: '/about', label: 'About' },
    { path: '/', label: 'Dashboard' },
    { path: '/trading', label: 'Trading' },
    { path: '/real-estate', label: 'Real Estate' },
    // { path: '/ontology', label: 'Ontology' }, // Moved to dropdown
  ];

  const ontologyItems = [
    { path: '/ontology/macro', label: 'Macro Graph', requiredRole: null },  // 모든 사용자
    { path: '/ontology/architecture', label: 'Architecture Graph', requiredRole: 'architect' },  // Architect/Admin만
  ];

  const adminItems = [
    { path: '/admin/indicators', label: '경제지표 관리' },
    { path: '/admin/neo4j', label: 'Neo4j 모니터링' },
    { path: '/admin/users', label: '사용자 관리' },
    { path: '/admin/logs', label: '로그 관리' },
    { path: '/admin/llm', label: 'LLM 모니터링' },
    { path: '/admin/multi-agent', label: 'Multi-Agent 모니터링' },
    { path: '/admin/rebalancing', label: '리밸런싱 관리' },
    { path: '/admin/files', label: '파일 업로드' },
  ];

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/');

  return (
    <>
      <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-md border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2">
              <div className="bg-blue-600 p-1.5 rounded-lg">
                <TrendingUp className="h-6 w-6 text-white" />
              </div>
              <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400">
                StockOverflow
              </span>
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden md:flex space-x-1 items-center">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${isActive(item.path)
                    ? 'text-white bg-zinc-800'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                    } `}
                >
                  {item.label}
                </Link>
              ))}

              {/* Ontology Dropdown */}
              <div className="relative group">
                <button className={`flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg transition-all ${location.pathname.startsWith('/ontology')
                  ? 'text-white bg-zinc-800'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                  } `}>
                  Ontology
                  <ChevronDown className="h-4 w-4" />
                </button>

                {/* Dropdown Menu */}
                <div className="absolute left-0 mt-0 w-48 bg-black border border-zinc-800 rounded-xl shadow-xl overflow-hidden opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 transform origin-top-left">
                  <div className="py-1">
                    {ontologyItems
                      .filter(item => !item.requiredRole || (item.requiredRole === 'architect' && isArchitect))
                      .map((item) => (
                        <Link
                          key={item.path}
                          to={item.path}
                          className="block px-4 py-2 text-sm text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                        >
                          {item.label}
                        </Link>
                      ))}
                  </div>
                </div>
              </div>

              {/* Admin Dropdown */}
              {isAdmin && (
                <div className="relative group">
                  <button className={`flex items-center gap-1 px-4 py-2 text-sm font-medium rounded-lg transition-all ${location.pathname.startsWith('/admin')
                    ? 'text-white bg-zinc-800'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800/50'
                    } `}>
                    Admin
                    <ChevronDown className="h-4 w-4" />
                  </button>

                  {/* Dropdown Menu */}
                  <div className="absolute right-0 mt-0 w-48 bg-black border border-zinc-800 rounded-xl shadow-xl overflow-hidden opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 transform origin-top-right">
                    <div className="py-1">
                      {adminItems.map((item) => (
                        <Link
                          key={item.path}
                          to={item.path}
                          className="block px-4 py-2 text-sm text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
                        >
                          {item.label}
                        </Link>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </nav>

            {/* Right Section */}
            <div className="hidden md:flex items-center space-x-4">
              <button className="p-2 text-zinc-500 hover:text-white transition-colors relative">
                <Bell className="h-5 w-5" />
                <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-red-500 rounded-full"></span>
              </button>
              {isAuthenticated ? (
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 border border-zinc-700 flex items-center justify-center text-xs font-bold text-white">
                    {user?.username?.charAt(0).toUpperCase()}
                  </div>
                  <button
                    onClick={() => { logout(); window.location.reload(); }}
                    className="text-sm text-zinc-400 hover:text-white transition-colors"
                  >
                    로그아웃
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setIsLoginModalOpen(true)}
                  className="text-sm text-zinc-400 hover:text-white transition-colors"
                >
                  로그인
                </button>
              )}
            </div>

            {/* Mobile menu button */}
            <div className="md:hidden flex items-center">
              <button
                onClick={() => setIsMenuOpen(!isMenuOpen)}
                className="text-zinc-400 hover:text-white p-2"
              >
                {isMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <div className="md:hidden bg-black border-b border-zinc-800">
            <div className="px-2 pt-2 pb-3 space-y-1 sm:px-3">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setIsMenuOpen(false)}
                  className={`block px-3 py-2 rounded-md text-base font-medium ${isActive(item.path)
                    ? 'text-white bg-zinc-800'
                    : 'text-zinc-400 hover:text-white'
                    } `}
                >
                  {item.label}
                </Link>
              ))}


              {/* Mobile Ontology Menu */}
              <div className="border-t border-zinc-800 pt-2 mt-2">
                <button
                  onClick={() => setIsOntologyOpen(!isOntologyOpen)}
                  className="w-full text-left px-3 py-2 text-zinc-400 hover:text-white flex items-center justify-between"
                >
                  <span className="font-bold text-zinc-300">Ontology</span>
                  <ChevronDown className={`h-4 w-4 transform transition-transform ${isOntologyOpen ? 'rotate-180' : ''} `} />
                </button>

                {isOntologyOpen && (
                  <div className="pl-4 space-y-1">
                    {ontologyItems
                      .filter(item => !item.requiredRole || (item.requiredRole === 'architect' && isArchitect))
                      .map((item) => (
                        <Link
                          key={item.path}
                          to={item.path}
                          onClick={() => setIsMenuOpen(false)}
                          className={`block px-3 py-2 rounded-md text-sm font-medium ${isActive(item.path)
                            ? 'text-white bg-zinc-800'
                            : 'text-zinc-500 hover:text-white'
                            } `}
                        >
                          {item.label}
                        </Link>
                      ))}
                  </div>
                )}
              </div>

              {/* Mobile Admin Menu */}
              {isAdmin && (
                <div className="border-t border-zinc-800 pt-2 mt-2">
                  <button
                    onClick={() => setIsAdminOpen(!isAdminOpen)}
                    className="w-full text-left px-3 py-2 text-zinc-400 hover:text-white flex items-center justify-between"
                  >
                    <span className="font-bold text-blue-400">Admin Menu</span>
                    <ChevronDown className={`h-4 w-4 transform transition-transform ${isAdminOpen ? 'rotate-180' : ''} `} />
                  </button>

                  {isAdminOpen && (
                    <div className="pl-4 space-y-1">
                      {adminItems.map((item) => (
                        <Link
                          key={item.path}
                          to={item.path}
                          onClick={() => setIsMenuOpen(false)}
                          className={`block px-3 py-2 rounded-md text-sm font-medium ${isActive(item.path)
                            ? 'text-white bg-zinc-800'
                            : 'text-zinc-500 hover:text-white'
                            } `}
                        >
                          {item.label}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="border-t border-zinc-800 pt-2 mt-2">
                {isAuthenticated ? (
                  <button
                    onClick={() => { logout(); setIsMenuOpen(false); window.location.reload(); }}
                    className="block w-full text-left px-3 py-2 text-zinc-400 hover:text-white"
                  >
                    로그아웃
                  </button>
                ) : (
                  <button
                    onClick={() => { setIsLoginModalOpen(true); setIsMenuOpen(false); }}
                    className="block w-full text-left px-3 py-2 text-zinc-400 hover:text-white"
                  >
                    로그인
                  </button>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      <LoginModal isOpen={isLoginModalOpen} onClose={() => setIsLoginModalOpen(false)} />
    </>
  );
};
