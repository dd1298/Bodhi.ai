import React, { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem("qp_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("qp_token");
    if (token && !user) {
      setLoading(true);
      api
        .get("/auth/me")
        .then((r) => {
          setUser(r.data);
          localStorage.setItem("qp_user", JSON.stringify(r.data));
        })
        .catch(() => {
          localStorage.removeItem("qp_token");
          localStorage.removeItem("qp_user");
        })
        .finally(() => setLoading(false));
    }
  }, []); // eslint-disable-line

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("qp_token", data.token);
    localStorage.setItem("qp_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const register = async (payload) => {
    const { data } = await api.post("/auth/register", payload);
    localStorage.setItem("qp_token", data.token);
    localStorage.setItem("qp_user", JSON.stringify(data.user));
    setUser(data.user);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("qp_token");
    localStorage.removeItem("qp_user");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
};
