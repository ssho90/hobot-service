import React, { useState } from 'react';
import { Search, Menu, X, TrendingUp, BarChart2, PieChart, Bell } from 'lucide-react';

export const Header: React.FC = () => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 bg-black/80 backdrop-blur-md border-b border-zinc-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <TrendingUp className="h-6 w-6 text-white" />
            </div>
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400">
              StockOverflow
            </span>
          </div>

          {/* Desktop Nav */}
          <nav className="hidden md:flex space-x-8">
            <a href="#" className="text-zinc-400 hover:text-white px-3 py-2 text-sm font-medium transition-colors">About</a>
            <a href="#" className="text-white bg-zinc-800 rounded-md px-3 py-2 text-sm font-medium transition-colors">Macro Dashboard</a>
            <a href="#" className="text-zinc-400 hover:text-white px-3 py-2 text-sm font-medium transition-colors">Trading</a>
            <a href="#" className="text-zinc-400 hover:text-white px-3 py-2 text-sm font-medium transition-colors">Admin</a>
          </nav>

          {/* Right Section */}
          <div className="hidden md:flex items-center space-x-4">
            <button className="p-2 text-zinc-500 hover:text-white transition-colors relative">
              <Bell className="h-5 w-5" />
              <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-red-500 rounded-full"></span>
            </button>
            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 border border-zinc-700"></div>
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
            <a href="#" className="text-zinc-400 hover:text-white block px-3 py-2 rounded-md text-base font-medium">About</a>
            <a href="#" className="text-white bg-zinc-800 block px-3 py-2 rounded-md text-base font-medium">Macro Dashboard</a>
            <a href="#" className="text-zinc-400 hover:text-white block px-3 py-2 rounded-md text-base font-medium">Trading</a>
            <a href="#" className="text-zinc-400 hover:text-white block px-3 py-2 rounded-md text-base font-medium">Admin</a>
          </div>
        </div>
      )}
    </header>
  );
};