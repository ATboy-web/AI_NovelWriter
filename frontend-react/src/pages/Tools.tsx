import { useState } from 'react'

const TOOL_CATEGORIES = [
  {
    id: 'elements', name: '元素库', icon: '📦',
    items: ['重生复仇', '系统激活', '被退婚', '意外传承', '废柴逆袭', '隐世高手', '退婚流', '赘婿逆袭']
  },
  {
    id: 'bridges', name: '桥段库', icon: '🌉',
    items: ['英雄救美', '误会分离', '真相大白', '绝境逢生', '师徒传承', '生死对决', '重逢时刻', '身份揭秘']
  },
  {
    id: 'descriptions', name: '描写库', icon: '✍️',
    items: ['外貌描写', '环境描写', '战斗描写', '情感描写', '美食描写', '建筑描写', '天气描写', '心理描写']
  },
  {
    id: 'dialogue', name: '对话推演', icon: '💬',
    items: ['正面对话', '暗中交锋', '情感交流', '谈判博弈', '审讯对话', '告别场景', '告白场景', '争吵场景']
  },
  {
    id: 'storyflow', name: '故事流', icon: '📖',
    items: ['正向推演', '反向推演', '分支推演', '冲突升级', '多线并行', '伏笔回收', '节奏控制', '高潮设计']
  },
  {
    id: 'style', name: '风格转换', icon: '🎨',
    items: ['文学风格', '通俗风格', '古典风格', '现代风格', '幽默风格', '严肃风格', '浪漫风格', '黑暗风格']
  },
]

export default function Tools() {
  const [activeCategory, setActiveCategory] = useState('elements')
  const [searchQuery, setSearchQuery] = useState('')
  const [customItems, setCustomItems] = useState<Record<string, string[]>>({})
  const [newItem, setNewItem] = useState('')

  const currentCategory = TOOL_CATEGORIES.find(c => c.id === activeCategory)
  const allItems = [
    ...(currentCategory?.items || []),
    ...(customItems[activeCategory] || []),
  ].filter(item => !searchQuery || item.includes(searchQuery))

  const addCustomItem = () => {
    if (!newItem.trim()) return
    setCustomItems(prev => ({
      ...prev,
      [activeCategory]: [...(prev[activeCategory] || []), newItem.trim()],
    }))
    setNewItem('')
  }

  const removeCustomItem = (category: string, index: number) => {
    setCustomItems(prev => ({
      ...prev,
      [category]: (prev[category] || []).filter((_, i) => i !== index),
    }))
  }

  return (
    <div>
      <div className="page-header">
        <h1>创作工具</h1>
        <p>丰富的创作素材和工具，助你灵感爆发</p>
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        {/* 分类列表 */}
        <div style={{ width: 200 }}>
          <div className="card">
            <h3 style={{ marginBottom: 12 }}>工具分类</h3>
            {TOOL_CATEGORIES.map(cat => (
              <div
                key={cat.id}
                style={{
                  padding: '10px 12px',
                  cursor: 'pointer',
                  borderRadius: 8,
                  marginBottom: 4,
                  background: activeCategory === cat.id ? 'rgba(99,102,241,0.15)' : 'transparent',
                  color: activeCategory === cat.id ? 'var(--accent-light)' : 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
                onClick={() => setActiveCategory(cat.id)}
              >
                <span>{cat.icon}</span>
                <span>{cat.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 内容区 */}
        <div style={{ flex: 1 }}>
          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3>{currentCategory?.icon} {currentCategory?.name}</h3>
              <input
                className="input"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索..."
                style={{ width: 200 }}
              />
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
              {allItems.map((item, i) => {
                const isCustom = (customItems[activeCategory] || []).includes(item)
                return (
                  <span key={i} className="tag" style={{ cursor: 'pointer' }}>
                    {item}
                    {isCustom && (
                      <span
                        style={{ marginLeft: 6, color: 'var(--error)' }}
                        onClick={() => removeCustomItem(activeCategory, (customItems[activeCategory] || []).indexOf(item))}
                      >
                        ×
                      </span>
                    )}
                  </span>
                )
              })}
            </div>

            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className="input"
                value={newItem}
                onChange={e => setNewItem(e.target.value)}
                placeholder="添加自定义内容..."
                style={{ flex: 1 }}
                onKeyDown={e => e.key === 'Enter' && addCustomItem()}
              />
              <button className="btn btn-primary" onClick={addCustomItem}>添加</button>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginBottom: 12 }}>快速操作</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <button className="btn btn-secondary">AI生成场景描写</button>
              <button className="btn btn-secondary">AI生成对话</button>
              <button className="btn btn-secondary">AI生成大纲</button>
              <button className="btn btn-secondary">AI风格分析</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
