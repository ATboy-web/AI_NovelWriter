import { useState, useRef, useEffect } from 'react'

export default function Editor() {
  const [content, setContent] = useState('')
  const [wordCount, setWordCount] = useState(0)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiLoading, setAiLoading] = useState(false)
  const [aiResult, setAiResult] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    setWordCount(content.replace(/\s/g, '').length)
  }, [content])

  const handleAiAction = async (action: string) => {
    if (!content.trim() && action !== 'generate') {
      alert('请先输入内容')
      return
    }
    setAiLoading(true)
    setAiResult('')
    try {
      const res = await fetch('http://localhost:8001/api/v1/generate/chapter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          novel_type: 'scifi',
          chapter_title: 'AI辅助',
          chapter_outline: aiPrompt || content.substring(0, 200),
          previous_content: content,
          model_type: 'local',
          max_tokens: 1000,
          temperature: 0.8,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setAiResult(data.content)
      } else {
        setAiResult(`AI生成失败: ${data.error || '未知错误'}`)
      }
    } catch (err) {
      setAiResult(`请求失败: ${err}`)
    } finally {
      setAiLoading(false)
    }
  }

  const insertAiResult = () => {
    if (aiResult) {
      setContent(prev => prev + '\n\n' + aiResult)
      setAiResult('')
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>写作编辑器</h1>
        <p>沉浸式写作体验，AI随时辅助创作</p>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* 编辑区 */}
        <div style={{ flex: 1 }}>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <div>
                <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                  字数: {wordCount}
                </span>
              </div>
              <div>
                <button className="btn btn-secondary" style={{ marginRight: 8 }} onClick={() => setContent('')}>
                  清空
                </button>
                <button className="btn btn-primary" onClick={() => {
                  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = 'novel.txt'
                  a.click()
                }}>
                  导出
                </button>
              </div>
            </div>
            <textarea
              ref={textareaRef}
              className="input"
              value={content}
              onChange={e => setContent(e.target.value)}
              placeholder="开始你的创作..."
              style={{ minHeight: 500, fontSize: 16, lineHeight: 1.8 }}
            />
          </div>
        </div>

        {/* AI辅助面板 */}
        <div style={{ width: 320 }}>
          <div className="card">
            <h3 style={{ marginBottom: 16 }}>AI辅助</h3>
            <div style={{ marginBottom: 12 }}>
              <input
                className="input"
                value={aiPrompt}
                onChange={e => setAiPrompt(e.target.value)}
                placeholder="输入AI指令..."
              />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              <button className="btn btn-secondary" onClick={() => handleAiAction('continue')} disabled={aiLoading}>
                续写
              </button>
              <button className="btn btn-secondary" onClick={() => handleAiAction('expand')} disabled={aiLoading}>
                扩写
              </button>
              <button className="btn btn-secondary" onClick={() => handleAiAction('polish')} disabled={aiLoading}>
                润色
              </button>
              <button className="btn btn-secondary" onClick={() => handleAiAction('rewrite')} disabled={aiLoading}>
                改写
              </button>
            </div>
            {aiLoading && <p style={{ color: 'var(--text-secondary)' }}>AI生成中...</p>}
            {aiResult && (
              <div>
                <h4 style={{ marginBottom: 8, fontSize: 14 }}>AI生成结果</h4>
                <div style={{
                  background: 'var(--bg-dark)',
                  padding: 12,
                  borderRadius: 8,
                  fontSize: 13,
                  maxHeight: 300,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                }}>
                  {aiResult}
                </div>
                <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={insertAiResult}>
                  插入到正文
                </button>
              </div>
            )}
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>快捷键</h3>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              <p>Ctrl+S - 保存</p>
              <p>F11 - 全屏模式</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
