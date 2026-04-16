import React from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { SignOut, Stack } from "@phosphor-icons/react";

const NavItem = ({ to, label, testid }) => (
  <NavLink
    to={to}
    end
    data-testid={testid}
    className={({ isActive }) =>
      `px-3 py-2 text-sm font-bold uppercase tracking-wider transition-colors ${
        isActive
          ? "bg-black text-white"
          : "text-black hover:bg-neutral-100"
      }`
    }
  >
    {label}
  </NavLink>
);

export default function Header() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <header className="border-b-2 border-black bg-white sticky top-0 z-40">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-4">
        <Link
          to="/"
          data-testid="app-logo-link"
          className="flex items-center gap-3 group"
        >
          <div className="w-10 h-10 bg-black flex items-center justify-center border-2 border-black group-hover:bg-[#002FA7] transition-colors">
            <Stack size={22} weight="fill" color="#FFC300" />
          </div>
          <div className="leading-none">
            <div className="font-display text-xl">QPGEN</div>
            <div className="overline text-neutral-500 text-[10px] mt-0.5">
              Question Paper Studio
            </div>
          </div>
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          <NavItem to="/" label="Dashboard" testid="nav-dashboard" />
          <NavItem to="/textbooks" label="Textbooks" testid="nav-textbooks" />
          <NavItem to="/papers/new" label="New Paper" testid="nav-new-paper" />
          <NavItem to="/qbank" label="Question Bank" testid="nav-qbank" />
        </nav>

        <div className="flex items-center gap-3">
          <div className="hidden sm:block text-right">
            <div className="text-sm font-bold">{user?.full_name}</div>
            <div className="overline text-neutral-500 text-[10px]">
              {user?.role}
            </div>
          </div>
          <button
            onClick={handleLogout}
            data-testid="logout-button"
            className="qp-btn qp-btn-secondary"
          >
            <SignOut size={16} weight="bold" />
            <span className="hidden sm:inline">Logout</span>
          </button>
        </div>
      </div>
    </header>
  );
}
