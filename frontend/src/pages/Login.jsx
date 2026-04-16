import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ArrowRight, BookOpen } from "@phosphor-icons/react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(email, password);
      toast.success("Welcome back");
      navigate("/");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#FAFAFA]">
      {/* Left side: Image panel */}
      <div
        className="hidden lg:block relative border-r-2 border-black"
        style={{
          backgroundImage:
            "url(https://images.pexels.com/photos/22039140/pexels-photo-22039140.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <div className="absolute inset-0 bg-white/75" />
        <div className="absolute inset-0 p-12 flex flex-col justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-black flex items-center justify-center">
              <BookOpen size={24} weight="fill" color="#FFC300" />
            </div>
            <div>
              <div className="font-display text-2xl leading-none">QPGEN</div>
              <div className="overline text-neutral-700 mt-1">
                Question Paper Studio
              </div>
            </div>
          </div>

          <div className="max-w-md">
            <div className="overline text-neutral-700 mb-4">// VOLUME 01</div>
            <h1 className="font-display text-5xl lg:text-6xl leading-[0.9] text-black">
              Design exams
              <br />
              <span className="text-[#002FA7]">algorithmically.</span>
            </h1>
            <p className="mt-6 text-neutral-700 max-w-sm">
              Upload any textbook. Extract topics automatically. Generate
              original, calibrated question papers — with multi-provider AI
              fallback built-in.
            </p>
          </div>

          <div className="overline text-neutral-600">
            © QPGEN — Academic control room
          </div>
        </div>
      </div>

      {/* Right side: Form */}
      <div className="flex items-center justify-center p-6 lg:p-12">
        <form
          onSubmit={onSubmit}
          data-testid="login-form"
          className="w-full max-w-md qp-card hard-shadow-static"
        >
          <div className="overline text-neutral-500 mb-2">// AUTH / 01</div>
          <h2 className="font-display text-4xl mb-2">Sign in.</h2>
          <p className="text-neutral-600 mb-8 text-sm">
            Enter your credentials to access the studio.
          </p>

          <div className="mb-4">
            <label className="qp-label">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="teacher@school.edu"
              className="qp-input"
              data-testid="login-email-input"
            />
          </div>

          <div className="mb-6">
            <label className="qp-label">Password</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="qp-input"
              data-testid="login-password-input"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="qp-btn qp-btn-primary w-full"
            data-testid="login-submit-button"
          >
            {submitting ? "Signing in..." : "Sign in"}
            <ArrowRight size={16} weight="bold" />
          </button>

          <p className="mt-6 text-sm text-neutral-600">
            No account yet?{" "}
            <Link
              to="/register"
              className="font-bold underline underline-offset-4 hover:text-[#002FA7]"
              data-testid="go-to-register-link"
            >
              Create one
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
