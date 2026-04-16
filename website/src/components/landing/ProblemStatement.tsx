export default function ProblemStatement() {
  return (
    <section id="problem" className="py-32 px-6 md:px-16 lg:px-24">
      <div className="max-w-6xl mx-auto gap-16 md:gap-24 items-center">
        {/* <h2 className="text-5xl md:text-6xl font-extralight tracking-normal leading-tight">
          Problem Statement
        </h2> */}
        <div className="space-y-6 text-lg font-light leading-relaxed tracking-wide">
          <p>
            Posture correction is not a detection problem but a{" "}
            <span className="font-normal">decision problem</span>.
          </p>
          <p>It is
          deeply tied to context, activity, motivation, and attention.</p>        
          <p>
            To achieve long-term posture correction, it&apos;s important for
            the system to know{" "}
            <span className="font-normal">
              when, how, and whether to intervene
            </span>{" "}
            at every single moment.
          </p>
        </div>
      </div>
    </section>
  );
}
