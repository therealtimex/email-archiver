import React, { useState, useEffect } from 'react';

const Card = ({ title, value, subValue, trend, icon }) => (
  <div className="glass p-6 rounded-2xl flex flex-col gap-2 min-w-[240px]">
    <div className="flex justify-between items-start">
      <span className="text-gray-400 text-sm font-medium">{title}</span>
      <span className="text-primary">{icon}</span>
    </div>
    <div className="text-3xl font-bold tracking-tight">{value}</div>
    {subValue && (
      <div className="flex gap-2 items-center text-xs">
        <span className={trend === 'up' ? 'text-green-400' : 'text-gray-500'}>{subValue}</span>
        {trend === 'up' && <span>↗</span>}
      </div>
    )}
  </div>
);

const Badge = ({ children, type }) => {
  const styles = {
    important: "bg-red-500/20 text-red-400 border-red-500/30",
    promo: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    transactional: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    newsletter: "bg-green-500/20 text-green-400 border-green-500/30",
    completed: "bg-green-500/20 text-green-400 border-green-500/30",
    archived: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    pending: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold border ${styles[type.toLowerCase()] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'}`}>
      {children}
    </span>
  );
};

function App() {
  const [stats, setStats] = useState({ total_archived: 0, classified: 0, extracted: 0 });
  const [emails, setEmails] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    fetchStats();
    fetchEmails();
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/stats');
      const data = await res.json();
      setStats(data);
    } catch (e) {
      console.error(e);
    }
  };

  const fetchEmails = async () => {
    try {
      const res = await fetch('/api/emails');
      const data = await res.json();
      setEmails(data);
    } catch (e) {
      console.error(e);
    }
  };

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      await fetch('/api/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'gmail', incremental: true })
      });
      // In a real app, we'd listen for status updates via SSE or WebSocket
      setTimeout(() => {
        setIsSyncing(false);
        fetchStats();
        fetchEmails();
      }, 3000);
    } catch (e) {
      setIsSyncing(false);
    }
  };

  return (
    <div className="min-h-screen w-full flex bg-[#0a0a0c] text-white overflow-hidden">
      {/* Sidebar */}
      <aside className="w-20 border-r border-white/10 flex flex-col items-center py-8 gap-12 glass z-10">
        <div className="w-10 h-10 bg-primary/20 rounded-xl flex items-center justify-center text-primary font-bold shadow-lg shadow-primary/20">
          E
        </div>
        <nav className="flex flex-col gap-8 text-gray-400">
          <button className="hover:text-white transition-colors"><div className="w-6 h-6 bg-white/5 rounded-md"></div></button>
          <button className="hover:text-white transition-colors"><div className="w-6 h-6 bg-white/5 rounded-md"></div></button>
          <button className="hover:text-white transition-colors"><div className="w-6 h-6 bg-white/5 rounded-md"></div></button>
          <button className="hover:text-white transition-colors"><div className="w-6 h-6 bg-white/5 rounded-md"></div></button>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col p-8 overflow-y-auto z-0 max-h-screen">
        <header className="mb-10 flex justify-between items-center">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
            Archive Intelligence
          </h1>
          <div className="flex gap-4 items-center">
            <span className="text-sm text-gray-500">v0.6.0 Stable</span>
            <div className="w-10 h-10 rounded-full bg-white/5 border border-white/10 overflow-hidden"></div>
          </div>
        </header>

        {/* Stats Grid */}
        <section className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          <Card
            title="TOTAL ARCHIVED"
            value={stats.total_archived.toLocaleString()}
            subValue="Last 30 days: +12%"
            trend="up"
            icon="📁"
          />
          <Card
            title="CLASSIFIED"
            value={stats.classified.toLocaleString()}
            subValue="Accuracy: 98.4%"
            trend="up"
            icon="🧠"
          />
          <Card
            title="AI EXTRACTED"
            value={stats.extracted.toLocaleString()}
            subValue="Real-time processing"
            trend=""
            icon="📊"
          />
        </section>

        {/* Sync Action */}
        <section className="flex flex-col items-center mb-16">
          <button
            onClick={handleSync}
            disabled={isSyncing}
            className={`relative w-48 h-48 rounded-full flex items-center justify-center transition-all ${isSyncing ? 'animate-pulse scale-95' : 'hover:scale-105 active:scale-95'}`}
          >
            <div className={`absolute inset-0 rounded-full bg-primary/20 blur-2xl transition-opacity ${isSyncing ? 'opacity-100' : 'opacity-50'}`}></div>
            <div className="absolute inset-0 rounded-full border-2 border-primary/30 animate-[spin_10s_linear_infinite]"></div>
            <div className="absolute inset-4 rounded-full border border-primary/20 border-dashed animate-[spin_15s_linear_infinite_reverse]"></div>
            <div className="relative glass w-36 h-36 rounded-full flex flex-col items-center justify-center gap-1 shadow-inner">
              <span className="text-xl font-bold tracking-widest">{isSyncing ? 'SYNCING' : 'SYNC'}</span>
              <span className="text-[10px] text-gray-400 uppercase tracking-tighter">
                {isSyncing ? 'Processing Data' : 'Initiate Backup'}
              </span>
              <div className="mt-2 text-primary">🔄</div>
            </div>
          </button>
        </section>

        {/* Recent Activity */}
        <section className="glass rounded-2xl overflow-hidden flex flex-col">
          <div className="p-6 border-b border-white/10 flex justify-between items-center">
            <h2 className="font-bold flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary shadow-sm shadow-primary"></span>
              Recent Synchronization Task
            </h2>
            <button className="text-xs text-gray-500 hover:text-white transition-colors">View All Archive</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="text-gray-500 uppercase text-[10px] tracking-widest border-b border-white/5">
                  <th className="px-6 py-4 font-medium">Subject</th>
                  <th className="px-6 py-4 font-medium">Sender</th>
                  <th className="px-6 py-4 font-medium">Date</th>
                  <th className="px-6 py-4 font-medium">Status</th>
                  <th className="px-6 py-4 font-medium">Classification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {emails.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="px-6 py-10 text-center text-gray-500">No emails archived yet. Run sync to begin.</td>
                  </tr>
                ) : emails.map((email, idx) => (
                  <tr key={idx} className="hover:bg-white/5 transition-colors group cursor-pointer">
                    <td className="px-6 py-4 whitespace-nowrap font-medium group-hover:text-primary transition-colors">
                      {email.subject}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-gray-400">
                      {email.from}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-[12px] text-gray-500">
                      {new Date(email.date).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <Badge type="completed">Completed</Badge>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {email.classification ? (
                        <Badge type={email.classification.category}>{email.classification.category}</Badge>
                      ) : (
                        <span className="text-gray-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
