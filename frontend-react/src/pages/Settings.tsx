import { useState, useEffect } from 'react'

interface Settings {
  api_provider: string
  api_url: string
  api_key: string
  model: string
  context_window: number
  temperature: number
  img_provider: string
  img_url: string
}

const DEFAULT_SETTINGS: Settings = {
  api_provider: 'ollama',
  api_url: 'http://localhost:11434',
  api_key: '',
  model: 'qwen3.6',
  context_window: 32000,
  temperature: 0.8,
  img_provider: 'comfyui',
  img_url: 'http://localhost:8188',
}

export default function Settings() {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem('ai_novel_settings')
    if (saved) {
      try { setSettings(JSON.parse(saved)) } catch {}
    }
  }, [])

  const handleSave = () => {
    localStorage.setItem('ai_novel_settings', JSON.stringify(settings))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const update = (key: keyof Settings, value: string | number) => {
    setSettings(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div>
      <div className="page-header">
        <h1>系统设置</h1>
        <p>配置AI模型和应用参数</p>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 16 }}>AI模型配置</h3>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>API提供商</label>
          <select
            className="input"
            value={settings.api_provider}
            onChange={e => update('api_provider', e.target.value)}
          >
            <option value="ollama">Ollama (本地)</option>
            <option value="openai">OpenAI</option>
            <option value="deepseek">DeepSeek</option>
            <option value="claude">Claude</option>
            <option value="custom">自定义</option>
          </select>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>API地址</label>
          <input
            className="input"
            value={settings.api_url}
            onChange={e => update('api_url', e.target.value)}
            placeholder="http://localhost:11434"
          />
        </div>
        {settings.api_provider !== 'ollama' && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>API密钥</label>
            <input
              className="input"
              type="password"
              value={settings.api_key}
              onChange={e => update('api_key', e.target.value)}
              placeholder="sk-..."
            />
          </div>
        )}
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>模型名称</label>
          <input
            className="input"
            value={settings.model}
            onChange={e => update('model', e.target.value)}
            placeholder="qwen3.6"
          />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>上下文窗口</label>
          <input
            className="input"
            type="number"
            value={settings.context_window}
            onChange={e => update('context_window', Number(e.target.value))}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>生成温度 (0-1)</label>
          <input
            className="input"
            type="number"
            step="0.1"
            min="0"
            max="1"
            value={settings.temperature}
            onChange={e => update('temperature', Number(e.target.value))}
          />
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 16 }}>文生图配置</h3>
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>图像生成服务</label>
          <select
            className="input"
            value={settings.img_provider}
            onChange={e => update('img_provider', e.target.value)}
          >
            <option value="comfyui">ComfyUI</option>
            <option value="sdwebui">SD WebUI</option>
            <option value="none">不使用</option>
          </select>
        </div>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 6, fontSize: 14 }}>服务地址</label>
          <input
            className="input"
            value={settings.img_url}
            onChange={e => update('img_url', e.target.value)}
            placeholder="http://localhost:8188"
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12 }}>
        <button className="btn btn-primary" onClick={handleSave}>
          {saved ? '已保存 ✓' : '保存设置'}
        </button>
        <button className="btn btn-secondary" onClick={() => setSettings(DEFAULT_SETTINGS)}>
          恢复默认
        </button>
      </div>
    </div>
  )
}
