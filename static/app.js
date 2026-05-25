document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize PDBe Molstar Viewer Instance
    const viewerContainer = document.getElementById('pdb-viewer');
    const viewerInstance = new PDBeMolstarPlugin();
    
    // Default config with premium dark styling
    const viewerConfig = {
        customData: {
            url: `/api/v3/structure/pdb/4ZQK?file_format=pdb`,
            format: 'pdb'
        },
        bgColor: { r: 10, g: 10, b: 15 }, // Space Black
        hideCanvasControls: true,         // Use our custom premium panels instead
        hideControls: true,
        alpha: false,
        subscribeEvents: true,
        lighting: 'directional',
    };
    
    // Render initial PDB 4ZQK structure via our streaming API
    viewerInstance.render(viewerContainer, viewerConfig);
    
    // Track current active state
    let currentPdb = '4ZQK';
    let currentStyle = 'cartoon';
    
    // 2. Load PDB Button Handler
    const pdbInput = document.getElementById('pdb-input');
    const loadBtn = document.getElementById('load-btn');
    
    loadBtn.addEventListener('click', () => {
        const pdbId = pdbInput.value.trim().toUpperCase();
        if (pdbId.length !== 4) {
            alert('请输入 4 位有效的 PDB ID 编号');
            return;
        }
        
        currentPdb = pdbId;
        loadBtn.disabled = true;
        loadBtn.textContent = '流式载入中...';
        
        // Dynamic payload update using our backend high-performance cache API
        viewerInstance.visual.update({
            customData: {
                url: `/api/v3/structure/pdb/${pdbId}?file_format=pdb`,
                format: 'pdb'
            }
        }).then(() => {
            loadBtn.disabled = false;
            loadBtn.textContent = '载入结构';
            
            // Mock pocket metadata update depending on PDB for scientific presentation
            if (pdbId === '4ZQK') {
                document.getElementById('pocket-count').textContent = 'Pocket #1 (ASP-52, GLU-108)';
                document.getElementById('affinity-val').textContent = '12.4 nM';
            } else {
                document.getElementById('pocket-count').textContent = 'Pocket #2 (TYR-73, PHE-120)';
                document.getElementById('affinity-val').textContent = '48.9 nM';
            }
        }).catch(err => {
            loadBtn.disabled = false;
            loadBtn.textContent = '载入结构';
            alert(`结构加载失败，请检查网络或后端是否开启: ${err}`);
        });
    });

    // 3. Render Styles Controls (Cartoon, Spacefill, Ball/Stick, Surface)
    const styleBtnCartoon = document.getElementById('style-cartoon');
    const styleBtnSpacefill = document.getElementById('style-spacefill');
    const styleBtnBallstick = document.getElementById('style-ballstick');
    const styleBtnSurface = document.getElementById('style-surface');
    
    const styleButtons = [styleBtnCartoon, styleBtnSpacefill, styleBtnBallstick, styleBtnSurface];
    
    function setActiveStyle(activeBtn, visualStyle) {
        styleButtons.forEach(btn => btn.classList.remove('active'));
        activeBtn.classList.add('active');
        currentStyle = visualStyle;
        
        // Update representation styling in Molstar
        // Note: For custom visual representation mappings, we can toggle visibility
        viewerInstance.visual.update({
            visualStyle: visualStyle
        });
    }
    
    styleBtnCartoon.addEventListener('click', () => setActiveStyle(styleBtnCartoon, 'cartoon'));
    styleBtnSpacefill.addEventListener('click', () => setActiveStyle(styleBtnSpacefill, 'spacefill'));
    styleBtnBallstick.addEventListener('click', () => setActiveStyle(styleBtnBallstick, 'ball-and-stick'));
    styleBtnSurface.addEventListener('click', () => setActiveStyle(styleBtnSurface, 'molecular-surface'));

    // 4. Color Schemes (Chain, Quality/pLDDT, Hydrophobicity)
    const colorBtnChain = document.getElementById('color-chain');
    const colorBtnQuality = document.getElementById('color-quality');
    const colorBtnHydro = document.getElementById('color-hydro');
    
    const colorButtons = [colorBtnChain, colorBtnQuality, colorBtnHydro];
    
    function setActiveColor(activeBtn, colorType) {
        colorButtons.forEach(btn => btn.classList.remove('active'));
        activeBtn.classList.add('active');
        
        // Molstar color schemes
        let colorTheme = 'chain';
        if (colorType === 'quality') colorTheme = 'plddt'; // standard pLDDT confidence coloring
        if (colorType === 'hydrophobicity') colorTheme = 'hydrophobicity';
        
        viewerInstance.visual.update({
            colorTheme: colorTheme
        });
    }
    
    colorBtnChain.addEventListener('click', () => setActiveColor(colorBtnChain, 'chain'));
    colorBtnQuality.addEventListener('click', () => setActiveColor(colorBtnQuality, 'quality'));
    colorBtnHydro.addEventListener('click', () => setActiveColor(colorBtnHydro, 'hydrophobicity'));

    // 5. Active Pocket Alignment & Focus (High-fidelity Smooth Zoom)
    const focusBtn = document.getElementById('focus-pocket-btn');
    focusBtn.addEventListener('click', () => {
        focusBtn.classList.add('active-action');
        setTimeout(() => focusBtn.classList.remove('active-action'), 1000);
        
        // Focus camera on binding residues (e.g. residues 52 and 108 on Chain A)
        // PDBe-molstar selects and focuses specific regions using structure query selectors
        const focusQuery = {
            data: [
                { struct_asym_id: 'A', residue_number: 52, color: { r: 255, g: 50, b: 100 }, focus: true },
                { struct_asym_id: 'A', residue_number: 108, color: { r: 255, g: 50, b: 100 }, focus: true }
            ],
            visualStyle: currentStyle
        };
        
        viewerInstance.visual.select(focusQuery);
    });

    // 6. Smooth interactive FPS Counter Simulation
    let lastTime = performance.now();
    let frameCount = 0;
    const fpsVal = document.getElementById('fps-val');
    
    function updateFPS() {
        const now = performance.now();
        frameCount++;
        if (now - lastTime >= 1000) {
            const actualFps = Math.min(60, Math.round((frameCount * 1000) / (now - lastTime)));
            fpsVal.textContent = actualFps;
            frameCount = 0;
            lastTime = now;
        }
        requestAnimationFrame(updateFPS);
    }
    requestAnimationFrame(updateFPS);
});
