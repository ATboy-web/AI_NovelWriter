import { useState } from 'react'

const NOVEL_TYPES = [
  { id: 'scifi', name: '科幻小说', icon: '🚀', desc: '未来科技、太空探索' },
  { id: 'mystery', name: '悬疑推理', icon: '🔍', desc: '逻辑推理、意外结局' },
  { id: 'romance', name: '言情小说', icon: '💕', desc: '情感细腻、浪漫氛围' },
  { id: 'fantasy', name: '奇幻小说', icon: '🐉', desc: '魔法世界、史诗冒险' },
  { id: 'urban', name: '都市小说', icon: '🏙️', desc: '现实背景、生活气息' },
  { id: 'history', name: '历史小说', icon: '📜', desc: '朝代更迭、权谋斗争' },
  { id: 'martial_arts', name: '武侠小说', icon: '⚔️', desc: '江湖恩怨、侠义精神' },
  { id: 'xianxia', name: '仙侠小说', icon: '✨', desc: '修仙渡劫、宗门纷争' },
  { id: 'horror', name: '恐怖小说', icon: '👻', desc: '恐怖氛围、心理恐惧' },
  { id: 'military', name: '军事小说', icon: '🎖️', desc: '战争场面、战友情谊' },
  { id: 'game', name: '游戏小说', icon: '🎮', desc: '游戏系统、升级打怪' },
  { id: 'sports', name: '体育小说', icon: '⚽', desc: '竞技比赛、热血拼搏' },
  { id: 'time_travel', name: '穿越小说', icon: '⏰', desc: '时空穿越、改变历史' },
  { id: 'system_flow', name: '系统流', icon: '📱', desc: '金手指、逆袭打脸' },
  { id: 'apocalypse', name: '末日小说', icon: '☢️', desc: '末世生存、人性考验' },
]

export default function Home() {
  const [title, setTitle] = useState('')
  const [synopsis, setSynopsis] = useState('')
  const [selectedType, setSelectedType] = useState('scifi')
  const [chapterCount, setChapterCount] = useState(10)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState('')

  const handleGenerate = async () => {
    if (!title.trim()) {
      alert('请输入小说标题')
      return
    }
    setGenerating(true)
    setResult('')
    try {
      const res = await fetch('http://localhost:8002/api/v1/novel/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          synopsis,
          novel_type: selectedType,
          chapter_count: chapterCount,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setResult(JSON.stringify(data, null, 2))
      } else {
        setResult(`生成失败: ${data.error || '未知错误'}`)
      }
    } catch (err) {
      setResult(`请求失败: ${err}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>AI小说创作工坊</h1>
        <p>选择小说类型，输入创意，AI帮你生成完整小说</p>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 16 }}>选择小说类型</h3>
        <div className="card-grid">
          {NOVEL_TYPES.map(t => (
            <div
              key={t.id}
              className={`card ${selectedType === t.id ? 'selected' : ''}`}
              style={{
                cursor: 'pointer',
                borderColor: selectedType === t.id ? 'var(--accent)' : undefined,
                background: selectedType === t.id ? 'rgba(99,102,241,0.1)' : undefined,
              }}
              onClick={() => setSelectedType(t.id)}
            >
              <div style={{ fontSize: 28, marginBottom: 8 }}>{t.icon}</div>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{t.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 16 }}>小说信息</h3>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>小说标题</label>
          <input
            className="input"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="输入小说标题..."
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>小说简介</label>
          <textarea
            className="input"
            value={synopsis}
            onChange={e => setSynopsis(e.target.value)}
            placeholder="输入小说简介或核心概念..."
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>章节数量</label>
          <input
            className="input"
            type="number"
            value={chapterCount}
            onChange={e => setChapterCount(Number(e.target.value))}
            min={1}
            max={100}
            style={{ width: 120 }}
          />
        </div>
        <button className="btn btn-primary" onClick={handleGenerate} disabled={generating}>
          {generating ? '生成中...' : '开始生成'}
        </button>
      </div>

      {result && (
        <div className="card">
          <h3 style={{ marginBottom: 12 }}>生成结果</h3>
          <pre style={{
            background: 'var(--bg-dark)',
            padding: 16,
            borderRadius: 8,
            overflow: 'auto',
            maxHeight: 400,
            fontSize: 13,
          }}>
            {result}
          </pre>
        </div>
      )}
    </div>
  )
}
