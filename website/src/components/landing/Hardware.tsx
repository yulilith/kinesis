import Image from "next/image";

export default function Hardware() {
  return (
    <section id="hardware" className="py-32 px-6 md:px-16 lg:px-24 bg-surface">
      <div className="max-w-6xl mx-auto">
        {/* Full-width product image */}
        <div className="relative w-full aspect-[21/9] rounded-2xl overflow-hidden mb-16">
          <Image
            src="/kinesis-product.png"
            alt="Kinesis wearable posture device on a person's back"
            fill
            className="object-cover object-center"
            priority
          />
        </div>

        {/* Text + SVG diagram */}
        <div className="grid md:grid-cols-2 gap-16 items-start">
          <div>
            <h2 className="text-5xl md:text-6xl font-extralight tracking-normal leading-tight mb-8">
              Kinesis Hardware
            </h2>
            <p className="text-lg font-light leading-relaxed tracking-wide text-muted mb-8">
              A lightweight wearable with dual IMU sensors along the spine and
              four vibration motors for directional haptic feedback.
            </p>
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-amber-300 border border-amber-400" />
                  <span className="text-sm font-light tracking-wide">
                    IMU x 2
                  </span>
                </div>
                <p className="text-xs font-light text-muted pl-6">
                  Upper &amp; lower spine tracking
                </p>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-purple-400" />
                  <span className="text-sm font-light tracking-wide">
                    Vibration motor x 4
                  </span>
                </div>
                <p className="text-xs font-light text-muted pl-6">
                  Directional haptic correction
                </p>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-gray-400" />
                  <span className="text-sm font-light tracking-wide">
                    ESP32
                  </span>
                </div>
                <p className="text-xs font-light text-muted pl-6">
                  On-board processing &amp; BLE
                </p>
              </div>
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-blue-300" />
                  <span className="text-sm font-light tracking-wide">
                    Meta AI Glasses
                  </span>
                </div>
                <p className="text-xs font-light text-muted pl-6">
                  Context sensing &amp; voice
                </p>
              </div>
            </div>
          </div>

          {/* SVG sensor placement diagram */}
          <div className="bg-white rounded-2xl p-8 shadow-sm">
            <svg
              viewBox="0 0 400 500"
              className="w-full max-w-sm mx-auto"
              xmlns="http://www.w3.org/2000/svg"
            >
              {/* Back silhouette */}
              <path
                d="M200 40 C240 40 270 60 275 90 C280 120 280 150 285 170
                   C290 190 310 200 320 220 C330 240 330 260 325 280
                   C320 300 310 320 305 340 C300 360 300 380 300 400
                   L100 400 C100 380 100 360 95 340 C90 320 80 300 75 280
                   C70 260 70 240 80 220 C90 200 110 190 115 170
                   C120 150 120 120 125 90 C130 60 160 40 200 40Z"
                fill="#f0e6d6"
                stroke="#d4c4b0"
                strokeWidth="1.5"
              />
              {/* Spine line */}
              <line x1="200" y1="80" x2="200" y2="360" stroke="#a855f7" strokeWidth="2.5" opacity="0.6" />
              {/* Shoulder line (dashed) */}
              <line x1="120" y1="190" x2="280" y2="190" stroke="#a855f7" strokeWidth="2" strokeDasharray="8 5" opacity="0.5" />
              {/* IMU sensors (yellow) */}
              <circle cx="200" cy="120" r="14" fill="#fde68a" stroke="#f59e0b" strokeWidth="2" />
              <text x="200" y="125" textAnchor="middle" fontSize="8" fontWeight="bold" fill="#92400e">IMU</text>
              <circle cx="200" cy="320" r="14" fill="#fde68a" stroke="#f59e0b" strokeWidth="2" />
              <text x="200" y="325" textAnchor="middle" fontSize="8" fontWeight="bold" fill="#92400e">IMU</text>
              {/* ESP32 chip */}
              <rect x="186" y="155" width="28" height="20" rx="3" fill="#374151" stroke="#555" strokeWidth="1" />
              <text x="200" y="168" textAnchor="middle" fontSize="6" fill="#9ca3af">ESP32</text>
              {/* Vibration motors (purple) */}
              <circle cx="200" cy="100" r="11" fill="#a855f7" opacity="0.85" />
              <text x="200" y="104" textAnchor="middle" fontSize="7" fill="white" fontWeight="bold">M</text>
              <circle cx="130" cy="190" r="11" fill="#a855f7" opacity="0.85" />
              <text x="130" y="194" textAnchor="middle" fontSize="7" fill="white" fontWeight="bold">M</text>
              <circle cx="270" cy="190" r="11" fill="#a855f7" opacity="0.85" />
              <text x="270" y="194" textAnchor="middle" fontSize="7" fill="white" fontWeight="bold">M</text>
              <circle cx="200" cy="340" r="11" fill="#a855f7" opacity="0.85" />
              <text x="200" y="344" textAnchor="middle" fontSize="7" fill="white" fontWeight="bold">M</text>
              {/* Labels */}
              <text x="240" y="122" fontSize="10" fill="#666">Upper spine</text>
              <text x="240" y="322" fontSize="10" fill="#666">Lower spine</text>
              <text x="285" y="194" fontSize="10" fill="#666">R. shoulder</text>
              <text x="60" y="194" fontSize="10" fill="#666">L. shoulder</text>
            </svg>
          </div>
        </div>
      </div>
    </section>
  );
}
