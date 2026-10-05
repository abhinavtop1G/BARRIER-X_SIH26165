import { useNavigate } from 'react-router-dom'
import Navbar from '@/components/Navbar'


function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="section-label">{children}</p>
}

function Metric({ val, label }: { val: string; label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-display text-2xl font-bold text-bx-gold leading-none">{val}</span>
      <span className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-muted">{label}</span>
    </div>
  )
}

function StepCard({ num, title, desc }: { num: string; title: string; desc: string }) {
  return (
    <div className="bg-bx-card border-r border-bx-border last:border-r-0 p-8 hover:bg-bx-hover transition-colors duration-200">
      <span className="font-mono text-[0.65rem] text-bx-gold tracking-widest block mb-5">{num}</span>
      <h4 className="font-display text-lg font-semibold text-bx-text mb-3">{title}</h4>
      <p className="text-sm text-bx-secondary leading-relaxed">{desc}</p>
    </div>
  )
}

interface CoreFeatureProps {
  title: string
  desc: string
  tag: string
}

function CoreFeatureCard({ title, desc, tag }: CoreFeatureProps) {
  return (
    <div className="card flex flex-col gap-4 p-7 bg-bx-card border border-bx-border rounded-xl hover:border-bx-gold/30 hover:bg-bx-hover transition-all duration-200">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-gold bg-bx-gold/10 border border-bx-gold/20 px-2.5 py-0.5 rounded-full">
          {tag}
        </span>
      </div>
      <h4 className="font-display text-lg font-bold text-bx-text leading-snug">{title}</h4>
      <p className="text-sm text-bx-secondary leading-relaxed">{desc}</p>
    </div>
  )
}


export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="bg-bx-bg min-h-dvh">
      <Navbar />

      <section className="relative min-h-dvh flex items-center pt-16 pb-20 border-b border-bx-border overflow-hidden">
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-1/3 right-0 w-[600px] h-[600px] bg-bx-gold/[0.03] rounded-full blur-[120px]" />
        </div>

        <div className="relative max-w-7xl mx-auto px-6 w-full">
          <p className="font-mono text-[0.65rem] uppercase tracking-widest text-bx-muted mb-8">
            Oil India Limited · HSSE Safety Digital Twin &amp; Safety Intelligence
          </p>

          <h1 className="font-display font-bold text-bx-text leading-[1.15] tracking-tight mb-7"
              style={{ fontSize: 'clamp(2.75rem, 6vw, 5rem)' }}>
            Identify Fatal Potential<br />
            <span className="text-bx-gold">Before It Becomes</span><br />
            an Incident.
          </h1>

          <p className="text-lg text-bx-secondary leading-relaxed max-w-[52ch] mb-10">
            BARRIER X uses AI-powered safety intelligence to analyze HSSE observations
            and surface reports with genuine Serious Injury or Fatality potential —
            so HSE teams can focus where it matters most.
          </p>

          <div className="flex flex-wrap gap-4 mb-16">
            <button onClick={() => navigate('/login')} className="btn-gold px-8 py-3.5 text-base">
              Enter BARRIER X
            </button>
            <button
              onClick={() => document.getElementById('core-features')?.scrollIntoView({ behavior: 'smooth' })}
              className="btn-ghost px-8 py-3.5 text-base"
            >
              Core Features
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-0 border-t border-bx-border pt-8">
            {[
              { val: '0.6667', label: 'PR-AUC'       },
              { val: '0.757',  label: 'ROC-AUC'      },
              { val: '80%',    label: 'Precision @10' },
              { val: '46 ms',  label: 'CPU · No GPU'  },
            ].map((m, i) => (
              <div key={m.label} className="flex items-center">
                {i > 0 && <div className="w-px h-8 bg-bx-border mx-8" />}
                <Metric {...m} />
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="core-features" className="border-b border-bx-border py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <SectionLabel>Core Capabilities</SectionLabel>
          <h2 className="font-display font-bold text-bx-text text-4xl leading-tight mb-4">
            Core Features of BARRIER X
          </h2>
          <p className="text-bx-secondary text-[1.0625rem] leading-relaxed max-w-[64ch] mb-14">
            Designed specifically for upstream oil &amp; gas operations, BARRIER X integrates predictive
            safety intelligence, spatial risk modeling, and conversational AI into a unified platform.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <CoreFeatureCard
              title="Real-Time SIF Risk Scoring"
              desc="Evaluates safety observations and near-miss narratives instantly using custom industrial NLP models trained to detect hidden fatal precursor signals."
              tag="ML Core"
            />
            <CoreFeatureCard
              title="3D Safety Digital Twin"
              desc="Visualizes spatial safety risk density across industrial assets, pipelines, and facilities in an interactive 3D digital model."
              tag="Digital Twin"
            />
            <CoreFeatureCard
              title="AI HSE Agent"
              desc="Conversational safety assistant providing RAG-powered risk insights, policy compliance checks, and evidence-based intervention recommendations."
              tag="AI Agent"
            />
            <CoreFeatureCard
              title="Calibrated Probability & Risk Banding"
              desc="Outputs calibrated SIF probability scores categorised into HIGH, ELEVATED, BORDERLINE, and LOW risk bands for clear decision-making."
              tag="Analytics"
            />
            <CoreFeatureCard
              title="Precursor Pattern Detection"
              desc="Identifies recurring activity–location–barrier-failure combinations before they converge into a serious incident."
              tag="Precursors"
            />
            <CoreFeatureCard
              title="Life-Saving Rule Mapping"
              desc="Automatically maps safety observation narratives to relevant IOGP Life-Saving Rules using multi-label classification."
              tag="Compliance"
            />
            <CoreFeatureCard
              title="Batch Narrative Prioritization"
              desc="Upload and score bulk safety datasets simultaneously. Automatically ranks high-potential incidents at the top for immediate inspection."
              tag="Batch API"
            />
            <CoreFeatureCard
              title="Actionable HSE Guidance"
              desc="Pairs every assessment with specific operational safety guidance and barrier verification steps based on recognized hazard patterns."
              tag="Safety First"
            />
            <CoreFeatureCard
              title="Industrial Transfer Learning Engine"
              desc="Domain-adapted on 590K safety observations and STILT fine-tuned on 73K high-consequence incident determinations."
              tag="Domain AI"
            />
          </div>
        </div>
      </section>

      <section id="problem" className="border-b border-bx-border py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <SectionLabel>The Challenge</SectionLabel>
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-24 items-center">
            <div>
              <h2 className="font-display font-bold text-bx-text text-4xl leading-tight mb-5">
                The Safety Data Problem
              </h2>
              <p className="text-bx-secondary leading-relaxed text-[1.0625rem]">
                Oil India Limited generates large volumes of safety observations, near-misses,
                and incident reports. Manual periodic review makes it difficult to identify
                the small fraction of reports with genuine fatal potential — especially when
                the actual outcome was minor or no injury.
              </p>
            </div>

            <div className="flex flex-col gap-0">
              <div className="card rounded-t-xl rounded-b-none">
                <p className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-gold mb-3">Actual Severity</p>
                <p className="text-sm text-bx-secondary leading-relaxed">
                  What physically happened — a near miss, minor injury, or no injury at all.
                </p>
              </div>
              <div className="text-center text-3xl text-bx-border font-display py-2 bg-bx-card border-x border-bx-border">≠</div>
              <div className="rounded-b-xl rounded-t-none p-6 bg-bx-gold/[0.04] border border-bx-gold/20">
                <p className="font-mono text-[0.6rem] uppercase tracking-widest text-bx-gold mb-3">Fatal Potential</p>
                <p className="text-sm text-bx-secondary leading-relaxed">
                  What <em>could</em> have happened. An event can have zero injuries and still
                  expose workers to a credible fatal consequence.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="solution" className="border-b border-bx-border py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <SectionLabel>How It Works</SectionLabel>
          <h2 className="font-display font-bold text-bx-text text-4xl leading-tight mb-4">
            From Safety Reports to Safety Intelligence
          </h2>
          <p className="text-bx-secondary text-[1.0625rem] leading-relaxed max-w-[60ch] mb-14">
            BARRIER X processes free-text HSSE narratives through a purpose-built AI pipeline,
            surfacing the events that deserve immediate attention.
          </p>

          <div className="border border-bx-border rounded-xl overflow-hidden grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 md:divide-x md:divide-bx-border divide-y md:divide-y-0 divide-bx-border">
            <StepCard num="01" title="Analyze"    desc="AI reads the safety narrative and identifies key signals — stored energy, isolation failures, proximity to personnel." />
            <StepCard num="02" title="Prioritize" desc="Reports are ranked by SIF potential so high-consequence events receive attention regardless of actual injury." />
            <StepCard num="03" title="Understand" desc="Calibrated probability scores and risk bands surface the evidence behind each classification." />
            <StepCard num="04" title="Act"        desc="The intelligence helps HSE teams prioritize investigations and target the highest-risk precursors." />
          </div>
        </div>
      </section>

      <section id="about" className="border-b border-bx-border py-24 lg:py-32">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-24 items-start">
            <div>
              <SectionLabel>About</SectionLabel>
              <h2 className="font-display font-bold text-bx-text text-4xl leading-tight mb-5">
                Built for Oil India Limited
              </h2>
              <p className="text-bx-secondary text-[1.0625rem] leading-relaxed mb-6">
                BARRIER X is an enterprise AI solution for Oil India Limited HSSE Safety Intelligence
                &amp; Digital Twin operations. The ML core uses DeBERTa-v3-small fine-tuned through
                a four-stage transfer learning pipeline, domain-adapted on 590K industrial safety
                narratives and intermediate-trained on 73K PHMSA serious-incident determinations.
              </p>
              <p className="text-sm text-bx-muted italic border-l-2 border-bx-subtle pl-4 leading-relaxed">
                This is a triage aid that ranks reports for human review. It does not replace human judgment.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-px bg-bx-border border border-bx-border rounded-xl overflow-hidden">
              {[
                { val: '590K',   label: 'Unlabelled narratives for domain adaptation'    },
                { val: '73K',    label: 'PHMSA rows for intermediate task training'       },
                { val: 'PR-AUC 0.67', label: 'On 123-report frozen held-out test set'   },
                { val: '46 ms', label: 'Inference latency, CPU, no GPU required'         },
              ].map(({ val, label }) => (
                <div key={val} className="bg-bx-card p-7 flex flex-col gap-2">
                  <span className="font-display text-2xl font-bold text-bx-gold leading-none">{val}</span>
                  <span className="text-xs text-bx-muted leading-relaxed">{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="py-28 border-b border-bx-border">
        <div className="max-w-7xl mx-auto px-6 text-center flex flex-col items-center gap-6">
          <h2 className="font-display font-bold text-bx-text text-5xl leading-tight">
            Turn Safety Reports Into<br />
            <span className="text-bx-gold">Early Warning Signals.</span>
          </h2>
          <p className="text-bx-secondary text-lg leading-relaxed max-w-[50ch]">
            Use BARRIER X to identify high-potential safety events and prioritize HSE
            attention before a serious incident occurs.
          </p>
          <button onClick={() => navigate('/login')} className="btn-gold px-10 py-4 text-base mt-2">
            Sign In to BARRIER X
          </button>
        </div>
      </section>

      <footer className="py-8">
        <div className="max-w-7xl mx-auto px-6 flex flex-col items-center gap-2 text-center">
          <span className="font-display text-lg font-bold tracking-widest uppercase">
            BARRIER<span className="text-bx-gold">X</span>
          </span>
          <p className="text-xs text-bx-muted">Oil India Limited HSSE Safety Intelligence Platform</p>
          <p className="text-xs text-bx-muted italic">Triage aid — rankings for human review only.</p>
        </div>
      </footer>
    </div>
  )
}
