import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import Home from './pages/Home'
import Editor from './pages/Editor'
import Tools from './pages/Tools'
import Settings from './pages/Settings'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app">
        <nav className="sidebar">
          <div className="logo">
            <h2>AI小说工坊</h2>
            <span className="version">v2.5.0</span>
          </div>
          <ul>
            <li><NavLink to="/" end>首页</NavLink></li>
            <li><NavLink to="/editor">写作</NavLink></li>
            <li><NavLink to="/tools">创作工具</NavLink></li>
            <li><NavLink to="/settings">设置</NavLink></li>
          </ul>
        </nav>
        <main className="content">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/editor" element={<Editor />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
