import React from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import { Toaster } from "sonner";

import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import Textbooks from "@/pages/Textbooks";
import NewPaper from "@/pages/NewPaper";
import PaperView from "@/pages/PaperView";
import SolutionView from "@/pages/SolutionView";
import QBank from "@/pages/QBank";
import Admin from "@/pages/Admin";
import AdminRoute from "@/components/AdminRoute";
import TeacherOrRedirect from "@/components/TeacherOrRedirect";
import StudentRoute from "@/components/StudentRoute";
import StudentDashboard from "@/pages/student/StudentDashboard";
import NewMockTest from "@/pages/student/NewMockTest";
import MockTestExam from "@/pages/student/MockTestExam";
import MockTestResult from "@/pages/student/MockTestResult";
import CompetitiveExams from "@/pages/CompetitiveExams";
import CompetitiveExamDetail from "@/pages/CompetitiveExamDetail";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <Toaster
            position="top-right"
            toastOptions={{
              style: {
                border: "2px solid #0A0A0A",
                borderRadius: 0,
                background: "#FFFFFF",
                color: "#0A0A0A",
                fontFamily: "IBM Plex Sans, sans-serif",
              },
            }}
          />
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/"
              element={
                <TeacherOrRedirect>
                  <Dashboard />
                </TeacherOrRedirect>
              }
            />
            <Route
              path="/textbooks"
              element={
                <ProtectedRoute>
                  <Textbooks />
                </ProtectedRoute>
              }
            />
            <Route
              path="/papers/new"
              element={
                <ProtectedRoute>
                  <NewPaper />
                </ProtectedRoute>
              }
            />
            <Route
              path="/papers/:id"
              element={
                <ProtectedRoute>
                  <PaperView />
                </ProtectedRoute>
              }
            />
            <Route
              path="/papers/:id/solution"
              element={
                <ProtectedRoute>
                  <SolutionView />
                </ProtectedRoute>
              }
            />
            <Route
              path="/qbank"
              element={
                <ProtectedRoute>
                  <QBank />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <AdminRoute>
                  <Admin />
                </AdminRoute>
              }
            />
            <Route
              path="/student"
              element={
                <StudentRoute>
                  <StudentDashboard />
                </StudentRoute>
              }
            />
            <Route
              path="/student/mock-tests/new"
              element={
                <StudentRoute>
                  <NewMockTest />
                </StudentRoute>
              }
            />
            <Route
              path="/student/mock-tests/:id"
              element={
                <StudentRoute>
                  <MockTestExam />
                </StudentRoute>
              }
            />
            <Route
              path="/student/mock-tests/:id/result"
              element={
                <StudentRoute>
                  <MockTestResult />
                </StudentRoute>
              }
            />
            <Route
              path="/competitive-exams"
              element={
                <ProtectedRoute>
                  <CompetitiveExams />
                </ProtectedRoute>
              }
            />
            <Route
              path="/competitive-exams/:id"
              element={
                <ProtectedRoute>
                  <CompetitiveExamDetail />
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
