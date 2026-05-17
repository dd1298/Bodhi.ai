import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

/**
 * Renders teacher/admin content for non-students, and redirects students to
 * their own dashboard. Use this to wrap the `/` route which historically
 * shows the teacher dashboard.
 */
export default function TeacherOrRedirect({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === "student") return <Navigate to="/student" replace />;
  return children;
}
