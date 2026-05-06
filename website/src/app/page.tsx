import Navbar from "../components/landing/Navbar";
import Hero from "../components/landing/Hero";
import ProblemStatement from "../components/landing/ProblemStatement";
import WhyMultiAgent from "../components/landing/WhyMultiAgent";
import Architecture from "../components/landing/Architecture";
import Hardware from "../components/landing/Hardware";
import DashboardDemo from "../components/dashboard/DashboardDemo";
import Network from "../components/landing/Network";
import TryKinesis from "../components/landing/TryKinesis";

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <ProblemStatement />
        <WhyMultiAgent />
        <Architecture />
        <Hardware />
        <DashboardDemo />
        <Network />
        <TryKinesis />

        <section className="py-24 px-6 md:px-16 lg:px-24 bg-surface">
          <div className="max-w-6xl mx-auto">
            <video
              src="/0416.mp4"
              controls
              playsInline
              muted
              className="w-full rounded-xl shadow-lg"
            />
          </div>
        </section>

        {/* Footer */}
        <footer className="py-16 px-6 md:px-16 lg:px-24 border-t border-border">
          <div className="max-w-6xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
            <div>
              <p className="font-extralight text-lg tracking-wide">Kinesis</p>
              <p className="text-xs font-light text-muted tracking-wider">
                MIT AI Agents (MAS.664) &middot; Spring 2026
              </p>
            </div>
            <p className="text-xs font-light text-muted tracking-wider">
              Chloe Ni &middot; Lilith Yu &middot; Nomy Yu
            </p>
          </div>
        </footer>
      </main>
    </>
  );
}
