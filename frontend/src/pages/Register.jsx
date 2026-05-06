import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { ArrowRight, BookOpen } from "@phosphor-icons/react";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "teacher",
  });
  const [submitting, setSubmitting] = useState(false);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await register(form);
      toast.success("Account created");
      navigate("/");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 bg-[#FAFAFA]">
      <div className="flex items-center justify-center p-6 lg:p-12 order-2 lg:order-1">
        <form
          onSubmit={onSubmit}
          data-testid="register-form"
          className="w-full max-w-md qp-card hard-shadow-static"
        >
          <div className="overline text-neutral-500 mb-2">// AUTH / 02</div>
          <h2 className="font-display text-4xl mb-2">Create account.</h2>
          <p className="text-neutral-600 mb-8 text-sm">
            Start generating high-quality question papers in minutes.
          </p>

          <div className="mb-4">
            <label className="qp-label">Full name</label>
            <input
              required
              value={form.full_name}
              onChange={onChange("full_name")}
              className="qp-input"
              placeholder="Jane Doe"
              data-testid="register-fullname-input"
            />
          </div>
          <div className="mb-4">
            <label className="qp-label">Email</label>
            <input
              type="email"
              required
              value={form.email}
              onChange={onChange("email")}
              className="qp-input"
              placeholder="teacher@school.edu"
              data-testid="register-email-input"
            />
          </div>
          <div className="mb-4">
            <label className="qp-label">Password</label>
            <input
              type="password"
              required
              minLength={6}
              value={form.password}
              onChange={onChange("password")}
              className="qp-input"
              placeholder="At least 6 characters"
              data-testid="register-password-input"
            />
          </div>
          <div className="mb-6">
            <label className="qp-label">Role</label>
            <div className="grid grid-cols-2 gap-0 border-2 border-black">
              {["teacher", "admin"].map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setForm({ ...form, role: r })}
                  data-testid={`register-role-${r}-button`}
                  className={`py-3 font-bold uppercase tracking-wider text-sm transition-colors ${
                    form.role === r
                      ? "bg-black text-white"
                      : "bg-white text-black hover:bg-neutral-100"
                  } ${r === "teacher" ? "border-r-2 border-black" : ""}`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="qp-btn qp-btn-primary w-full"
            data-testid="register-submit-button"
          >
            {submitting ? "Creating..." : "Create account"}
            <ArrowRight size={16} weight="bold" />
          </button>

          <p className="mt-6 text-sm text-neutral-600">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-bold underline underline-offset-4 hover:text-[#002FA7]"
              data-testid="go-to-login-link"
            >
              Sign in
            </Link>
          </p>
        </form>
      </div>

      <div
        className="hidden lg:block relative border-l-2 border-black order-1 lg:order-2"
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
              <div className="brand-mark text-2xl leading-none">
                Bodhi<span className="accent">.ai</span>
              </div>
              <div className="overline text-neutral-700 mt-1">
                Question Paper Studio
              </div>
            </div>
          </div>
          <div>
            <div className="overline text-neutral-700 mb-4">// VOLUME 02</div>
            <h1 className="font-display text-5xl lg:text-6xl leading-[0.9]">
              Join the
              <br />
              <span className="text-[#002FA7]">Bodhi.ai studio.</span>
            </h1>
          </div>
          <div className="overline text-neutral-600">© Bodhi.ai</div>
        </div>
      </div>
    </div>
  );
}
