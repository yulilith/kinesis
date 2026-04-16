export default function Hero() {
  return (
    <section className="relative h-screen overflow-hidden">
      {/* Background image with blur */}
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={{ backgroundImage: "url('/kinesis-bg.png')" }}
      >
        <div className="absolute inset-0 backdrop-blur-sm bg-black/15" />
      </div>

      {/* Content — dead center of viewport */}
      <div className="absolute inset-0 flex items-center justify-center z-10">
        <div className="text-center">
          <h1 className="text-9xl md:text-[12rem] font-extralight leading-none mb-6 text-white" style={{ letterSpacing: "-0.06em" }}>
            KINESIS
          </h1>
          <p className="text-lg md:text-xl font-extralight text-black/70 max-w-xl mx-auto leading-relaxed tracking-wide">
            A multi-agent embodied AI system for adaptive posture correction
          </p>
          <div className="mt-12">
            <a
              href="#demo"
              className="inline-block px-8 py-3 border border-black/30 text-black rounded-full text-sm font-light tracking-wider hover:bg-white hover:text-foreground transition-all"
            >
              See it in action
            </a>
          </div>
        </div>
      </div>

      {/* Team credits — bottom */}
      <p className="absolute bottom-12 left-0 right-0 text-center z-10 text-xs font-light text-black/50 tracking-wider">
        Chloe Ni &middot; Lilith Yu &middot; Nomy Yu
      </p>
    </section>
  );
}
