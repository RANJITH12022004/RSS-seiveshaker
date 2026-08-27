// Sieve Shaker CFR — Quick Test, recipe, and test-run UI (overrides friability helpers)

(function () {
    'use strict';

    window._quickLogicalSegments = window._quickLogicalSegments || [];
    window._recipeLogicalSegments = window._recipeLogicalSegments || [];

    function getQuickShakerMode() {
        var selected = document.querySelector('input[name="quick-shaker-mode"]:checked');
        var mode = selected ? String(selected.value || '').toUpperCase() : 'CONTINUOUS';
        if (mode === 'INTERMITTENT' || mode === 'LOGICAL') return mode;
        return 'CONTINUOUS';
    }

    function getRecipeShakerMode() {
        var selected = document.querySelector('input[name="recipe-shaker-mode"]:checked');
        var mode = selected ? String(selected.value || '').toUpperCase() : 'CONTINUOUS';
        if (mode === 'INTERMITTENT' || mode === 'LOGICAL') return mode;
        return 'CONTINUOUS';
    }

    function shakerModeLabel(mode) {
        var m = String(mode || '').toUpperCase();
        if (m === 'INTERMITTENT') return 'Intermittent';
        if (m === 'LOGICAL') return 'Logical';
        return 'Continuous';
    }

    function computeLogicalTotalSeconds(segments) {
        var total = 0;
        (segments || []).forEach(function (seg) {
            var sec = typeof parseMmSsToSeconds === 'function'
                ? parseMmSsToSeconds(seg.duration || seg.durationMmSs || '')
                : null;
            if (sec == null) sec = parseInt(seg.durationSeconds, 10);
            if (!isNaN(sec) && sec > 0) total += sec;
        });
        return total;
    }

    function renderLogicalSegments(listId, segments, totalId, prefix) {
        var listEl = document.getElementById(listId);
        if (!listEl) return;
        listEl.innerHTML = '';
        (segments || []).forEach(function (seg, idx) {
            var row = document.createElement('div');
            row.className = 'form-group logical-segment-row';
            row.innerHTML =
                '<label>Segment ' + (idx + 1) + ' (' + (seg.type === 'wait' ? 'Wait' : 'Run') + ')</label>' +
                '<input type="text" class="input-field logical-segment-duration" data-idx="' + idx + '" value="' +
                (seg.duration || formatSecondsToMmSs(seg.durationSeconds || 60)) + '" placeholder="MM:SS">' +
                '<button type="button" class="btn btn-secondary logical-segment-remove" data-idx="' + idx + '">Remove</button>';
            listEl.appendChild(row);
        });
        listEl.querySelectorAll('.logical-segment-duration').forEach(function (input) {
            input.addEventListener('change', function () {
                syncLogicalSegmentsFromDom(prefix);
            });
        });
        listEl.querySelectorAll('.logical-segment-remove').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var i = parseInt(btn.getAttribute('data-idx'), 10);
                var arr = prefix === 'recipe' ? window._recipeLogicalSegments : window._quickLogicalSegments;
                arr.splice(i, 1);
                renderLogicalSegments(listId, arr, totalId, prefix);
            });
        });
        var totalEl = document.getElementById(totalId);
        if (totalEl) {
            syncLogicalSegmentsFromDom(prefix);
            var totalSec = computeLogicalTotalSeconds(prefix === 'recipe' ? window._recipeLogicalSegments : window._quickLogicalSegments);
            totalEl.textContent = 'Total program time: ' + formatSecondsToMmSs(totalSec);
        }
    }

    function syncLogicalSegmentsFromDom(prefix) {
        var listId = prefix === 'recipe' ? 'recipe-logical-segments-list' : 'quick-logical-segments-list';
        var arr = prefix === 'recipe' ? window._recipeLogicalSegments : window._quickLogicalSegments;
        var listEl = document.getElementById(listId);
        if (!listEl) return arr;
        var rows = listEl.querySelectorAll('.logical-segment-row');
        rows.forEach(function (row, idx) {
            var input = row.querySelector('.logical-segment-duration');
            var sec = input ? parseMmSsToSeconds(input.value) : null;
            if (arr[idx]) {
                arr[idx].duration = input ? input.value : arr[idx].duration;
                arr[idx].durationSeconds = sec != null ? sec : arr[idx].durationSeconds;
            }
        });
        return arr;
    }

    window.addQuickLogicalSegment = function (type) {
        window._quickLogicalSegments.push({ type: type === 'wait' ? 'wait' : 'run', duration: '01:00', durationSeconds: 60 });
        renderLogicalSegments('quick-logical-segments-list', window._quickLogicalSegments, 'quick-logical-total-time', 'quick');
    };

    window.addRecipeLogicalSegment = function (type) {
        window._recipeLogicalSegments.push({ type: type === 'wait' ? 'wait' : 'run', duration: '01:00', durationSeconds: 60 });
        renderLogicalSegments('recipe-logical-segments-list', window._recipeLogicalSegments, 'recipe-logical-total-time', 'recipe');
    };

    window.updateLogicalCycles = function (prefix) {
        var totalSec = (typeof parseMmSsToSeconds === 'function' ? parseMmSsToSeconds((document.getElementById(prefix + '-logical-total-duration') || {}).value) : 0) || 0;
        var runSec   = (typeof parseMmSsToSeconds === 'function' ? parseMmSsToSeconds((document.getElementById(prefix + '-logical-run-time') || {}).value) : 0) || 0;
        var waitSec  = (typeof parseMmSsToSeconds === 'function' ? parseMmSsToSeconds((document.getElementById(prefix + '-logical-wait-time') || {}).value) : 0) || 0;
        var infoEl   = document.getElementById(prefix + '-logical-cycle-info');
        if (!infoEl) return;
        if (totalSec < 1 || runSec < 1) { infoEl.textContent = 'Enter valid times above'; return; }
        var cycleSec  = runSec + waitSec;
        var cycles    = cycleSec > 0 ? Math.floor(totalSec / cycleSec) : 0;
        var remainder = totalSec - cycles * cycleSec;
        var fmt = typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs : function(s){ var m=Math.floor(s/60); return (m<10?'0'+m:m)+':'+(s%60<10?'0'+s%60:s%60); };
        infoEl.innerHTML = 'Cycles: <strong>' + cycles + '</strong> &nbsp;|&nbsp; Run: ' + fmt(runSec) +
            (waitSec > 0 ? ' &nbsp;|&nbsp; Wait: ' + fmt(waitSec) : '') +
            (remainder > 0 ? ' &nbsp;|&nbsp; Remainder: ' + fmt(remainder) : '') +
            ' &nbsp;|&nbsp; Total: ' + fmt(totalSec);
    };

    window.applyQuickShakerModeToFields = function () {
        var mode = getQuickShakerMode();
        var durationWrap = document.getElementById('quick-duration-wrap');
        var onWrap = document.getElementById('quick-on-time-wrap');
        var offWrap = document.getElementById('quick-off-time-wrap');
        var logicalWrap = document.getElementById('quick-logical-segments-wrap');
        var isLogical = mode === 'LOGICAL';
        // Intermittent: firmware owns on/off pulse timing (command letter I). No UI on/off.
        // Logical: run/wait cycle inputs live in the logical wrap.
        if (durationWrap) durationWrap.style.display = isLogical ? 'none' : '';
        if (onWrap) onWrap.style.display = 'none';
        if (offWrap) offWrap.style.display = 'none';
        if (logicalWrap) logicalWrap.style.display = isLogical ? '' : 'none';
        if (isLogical) updateLogicalCycles('quick');
    };

    window.applyRecipeShakerModeToFields = function () {
        var mode = getRecipeShakerMode();
        var durationWrap = document.getElementById('recipe-duration-wrap');
        var onWrap = document.getElementById('recipe-on-time-wrap');
        var offWrap = document.getElementById('recipe-off-time-wrap');
        var logicalWrap = document.getElementById('recipe-logical-segments-wrap');
        var isLogical = mode === 'LOGICAL';
        if (durationWrap) durationWrap.style.display = isLogical ? 'none' : '';
        if (onWrap) onWrap.style.display = 'none';
        if (offWrap) offWrap.style.display = 'none';
        if (logicalWrap) logicalWrap.style.display = isLogical ? '' : 'none';
        if (isLogical) updateLogicalCycles('recipe');
    };

    window.applyWeighMethod = function () {};

    var _scalePollers = {};
    var _wzOnWeight = null;

    window.startScalePoll = function (prefix) {
        stopScalePoll(prefix);
        _scalePollers[prefix] = setInterval(function () {
            fetch((typeof API_BASE !== 'undefined' ? API_BASE : '') + '/api/scale/read')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    // Never accept simulated/fake weights — stay on Waiting until real scale.
                    if (!data || !data.ok || data.simulated) return;
                    if (data.weight == null || parseFloat(data.weight) <= 0) return;
                    if (_wzOnWeight) _wzOnWeight(parseFloat(data.weight));
                })
                .catch(function () {});
        }, 800);
    };

    window.stopScalePoll = function (prefix) {
        if (_scalePollers[prefix]) { clearInterval(_scalePollers[prefix]); delete _scalePollers[prefix]; }
    };

    window.fetchWeightFromScale = function () {};

    function getInitialWeight() { return _sr.sampleWeight || 0; }
    function getWeighMethod() { return (_sr.recipe && _sr.recipe.weighMethod) || 'automatic'; }

    function getReportWeighMethod() {
        if (_sr.manualWeighUsed) return 'manual';
        return getWeighMethod();
    }

    function _srCaptureRunElapsed() {
        var local = _sr.pollStartTime ? Math.floor((Date.now() - _sr.pollStartTime) / 1000) : 0;
        var backend = Math.floor(_sr.elapsedSeconds || 0);
        return Math.max(local, backend, 0);
    }

    function _wzParseManualWeight(raw) {
        var s = String(raw || '').trim();
        if (!s || !/^\d+(\.\d{1,4})?$/.test(s)) return null;
        var v = parseFloat(s);
        if (isNaN(v) || v <= 0) return null;
        return Math.round(v * 10000) / 10000;
    }

    // Full ASTM sieve table from ASTM/USP standard (mesh number + microns + mm)
    var ASTM_SIEVES = [
        { mesh: 'No. 3½', micron: 5600, mm: '5.600' },
        { mesh: 'No. 4',  micron: 4750, mm: '4.750' },
        { mesh: 'No. 5',  micron: 4000, mm: '4.000' },
        { mesh: 'No. 6',  micron: 3350, mm: '3.350' },
        { mesh: 'No. 7',  micron: 2800, mm: '2.800' },
        { mesh: 'No. 8',  micron: 2360, mm: '2.360' },
        { mesh: 'No. 10', micron: 2000, mm: '2.000' },
        { mesh: 'No. 12', micron: 1700, mm: '1.700' },
        { mesh: 'No. 14', micron: 1400, mm: '1.400' },
        { mesh: 'No. 16', micron: 1180, mm: '1.180' },
        { mesh: 'No. 18', micron: 1000, mm: '1.000' },
        { mesh: 'No. 20', micron: 850,  mm: '0.850' },
        { mesh: 'No. 25', micron: 710,  mm: '0.710' },
        { mesh: 'No. 30', micron: 600,  mm: '0.600' },
        { mesh: 'No. 35', micron: 500,  mm: '0.500' },
        { mesh: 'No. 40', micron: 425,  mm: '0.425' },
        { mesh: 'No. 45', micron: 355,  mm: '0.355' },
        { mesh: 'No. 50', micron: 300,  mm: '0.300' },
        { mesh: 'No. 60', micron: 250,  mm: '0.250' },
        { mesh: 'No. 70', micron: 212,  mm: '0.212' },
        { mesh: 'No. 80', micron: 180,  mm: '0.180' },
        { mesh: 'No. 100',micron: 150,  mm: '0.150' },
        { mesh: 'No. 120',micron: 125,  mm: '0.125' },
        { mesh: 'No. 140',micron: 106,  mm: '0.106' },
        { mesh: 'No. 170',micron: 90,   mm: '0.090' },
        { mesh: 'No. 200',micron: 75,   mm: '0.075' },
        { mesh: 'No. 230',micron: 63,   mm: '0.063' },
        { mesh: 'No. 270',micron: 53,   mm: '0.053' },
        { mesh: 'No. 325',micron: 45,   mm: '0.045' },
        { mesh: 'No. 400',micron: 38,   mm: '0.038' },
        { mesh: 'No. 450',micron: 32,   mm: '0.032' },
        { mesh: 'No. 500',micron: 25,   mm: '0.025' },
        { mesh: 'No. 635',micron: 20,   mm: '0.020' }
    ];

    var _micronPickerState = { prefix: '', sieveIdx: 0 };

    function _applyMicronToSieveButton(prefix, idx, micron, mesh) {
        var btn = document.getElementById(prefix + '-sieve-size-' + idx);
        var hidden = document.getElementById(prefix + '-sieve-val-' + idx);
        if (btn) {
            btn.innerHTML = '<span class="mb-mesh">' + (mesh || ('#' + micron)) + '</span>' +
                '<span class="mb-micron">' + micron + ' \u00b5m</span>';
            btn.dataset.value = String(micron);
            btn.classList.add('selected');
        }
        if (hidden) hidden.value = String(micron);
    }

    function _meshLabelForMicron(micron) {
        for (var aj = 0; aj < ASTM_SIEVES.length; aj++) {
            if (ASTM_SIEVES[aj].micron === micron) return ASTM_SIEVES[aj].mesh;
        }
        return '';
    }

    var _sieveRowCounts = { quick: 5, recipe: 5 };

    window.clampNumSievesInput = function (prefix) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        if (!numEl) return;
        var raw = parseInt(numEl.value, 10);
        var n = isNaN(raw) ? 1 : Math.max(1, Math.min(8, raw));
        numEl.value = String(n);
        _sieveRowCounts[prefix] = n;
        renderSieveSizeFields(prefix, true);
    };

    window.renderSieveSizeFields = function (prefix, preserve) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        var wrapEl = document.getElementById(prefix + '-sieve-sizes-wrap');
        if (!numEl || !wrapEl) return;
        var raw = parseInt(numEl.value, 10);
        var isFocused = document.activeElement === numEl;
        var n;
        if (!isNaN(raw) && raw >= 1 && raw <= 8) {
            n = raw;
        } else {
            n = _sieveRowCounts[prefix] || 5;
        }
        _sieveRowCounts[prefix] = n;
        if (!isFocused && (isNaN(raw) || raw < 1 || raw > 8)) {
            numEl.value = String(n);
        }
        var saved = {};
        if (preserve !== false) {
            for (var si = 1; si <= 8; si++) {
                var hid = document.getElementById(prefix + '-sieve-val-' + si);
                var btn0 = document.getElementById(prefix + '-sieve-size-' + si);
                var v = hid ? parseInt(hid.value, 10) : (btn0 ? parseInt(btn0.dataset.value, 10) : 0);
                if (!isNaN(v) && v > 0) saved[si] = v;
            }
        }
        var html = '<h3 class="create-recipe-section-title">Sieve Sizes \u2014 Sieve 1 = smallest, Sieve ' + n + ' = largest</h3><div class="form-grid create-recipe-form-grid">';
        for (var i = 1; i <= n; i++) {
            html += '<div class="form-group"><label>Sieve ' + i + '</label>' +
                '<button type="button" class="micron-pick-btn" id="' + prefix + '-sieve-size-' + i + '" data-value="" onclick="openMicronPicker(\'' + prefix + '\',' + i + ')">' +
                'Select Sieve</button>' +
                '<input type="hidden" id="' + prefix + '-sieve-val-' + i + '" value="">' +
                '<span id="' + prefix + '-sieve-warn-' + i + '" class="sieve-order-warn" style="color:#ef4444;font-size:11px;display:none;"></span></div>';
        }
        html += '<div class="form-group"><label>PAN (Receiver)</label>' +
            '<div class="micron-pick-btn micron-pan-fixed">Receiver</div></div>';
        html += '</div>';
        wrapEl.innerHTML = html;
        Object.keys(saved).forEach(function (key) {
            var idx = parseInt(key, 10);
            if (idx < 1 || idx > n) return;
            var micron = saved[key];
            _applyMicronToSieveButton(prefix, idx, micron, _meshLabelForMicron(micron));
        });
        if (typeof validateSieveOrder === 'function') validateSieveOrder(prefix);
    };

    window.openMicronPicker = function (prefix, sieveIdx) {
        if (typeof closeOSK === 'function') {
            try { closeOSK(); } catch (e) {}
        }
        _micronPickerState.prefix = prefix;
        _micronPickerState.sieveIdx = sieveIdx;
        var overlay = document.getElementById('micron-picker-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'micron-picker-overlay';
            overlay.className = 'micron-picker-overlay';
            document.body.appendChild(overlay);
        }
        var html = '<div class="micron-picker-panel">' +
            '<div class="micron-picker-title">Select Sieve Size &mdash; Sieve ' + sieveIdx + '</div>' +
            '<div class="micron-picker-grid">';
        for (var j = 0; j < ASTM_SIEVES.length; j++) {
            var sv = ASTM_SIEVES[j];
            html += '<button class="micron-btn" data-micron="' + sv.micron + '" onclick="pickMicronValue(' + sv.micron + ',\'' + sv.mesh + '\')">' +
                '<span class="mb-mesh">' + sv.mesh + '</span>' +
                '<span class="mb-micron">' + sv.micron + ' \u00b5m</span>' +
                '</button>';
        }
        html += '</div><button class="micron-picker-cancel" onclick="closeMicronPicker()">Cancel</button></div>';
        overlay.innerHTML = html;
        overlay.style.display = 'flex';
    };

    window.pickMicronValue = function (micron, mesh) {
        var prefix = _micronPickerState.prefix;
        var idx = _micronPickerState.sieveIdx;
        _applyMicronToSieveButton(prefix, idx, micron, mesh);
        closeMicronPicker();
        validateSieveOrder(prefix);
    };

    window.closeMicronPicker = function () {
        var overlay = document.getElementById('micron-picker-overlay');
        if (overlay) overlay.style.display = 'none';
    };

    window.validateSieveOrder = function (prefix) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        var n = Math.max(1, Math.min(8, parseInt((numEl || {}).value, 10) || 5));
        var valid = true;
        var prevVal = 0;
        for (var i = 1; i <= n; i++) {
            var btn = document.getElementById(prefix + '-sieve-size-' + i);
            var hidden = document.getElementById(prefix + '-sieve-val-' + i);
            var warn = document.getElementById(prefix + '-sieve-warn-' + i);
            var val = hidden ? parseInt(hidden.value, 10) || 0 : (btn ? parseInt(btn.dataset.value, 10) || 0 : 0);
            if (val > 0 && prevVal > 0 && val < prevVal) {
                if (warn) { warn.textContent = 'Must be \u2265 ' + prevVal + ' \u00b5m (sieve below)'; warn.style.display = ''; }
                if (btn) btn.style.outline = '2px solid #ef4444';
                valid = false;
            } else {
                if (warn) warn.style.display = 'none';
                if (btn) btn.style.outline = '';
            }
            if (val > 0) prevVal = val;
        }
        return valid;
    };

    function getSieveAnalysisFlag(prefix) {
        var sel = document.querySelector('input[name="' + prefix + '-sieve-analysis"]:checked');
        var v = sel ? String(sel.value || 'on').toLowerCase() : 'on';
        return v !== 'off';
    }

    function setSieveAnalysisFlag(prefix, enabled) {
        var val = enabled === false ? 'off' : 'on';
        var radio = document.querySelector('input[name="' + prefix + '-sieve-analysis"][value="' + val + '"]');
        if (radio) radio.checked = true;
    }

    function collectSieveData(prefix) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        var rawN = parseInt((numEl || {}).value, 10);
        var n = Math.max(1, Math.min(8, isNaN(rawN) ? 1 : rawN));
        var sizes = [];
        for (var i = 1; i <= n; i++) {
            var hidden = document.getElementById(prefix + '-sieve-val-' + i);
            var btn = document.getElementById(prefix + '-sieve-size-' + i);
            var v = hidden ? parseInt(hidden.value, 10) : (btn ? parseInt(btn.dataset.value, 10) : 0);
            sizes.push(isNaN(v) ? 0 : v);
        }
        return { numSieves: n, sieveSizes: sizes, sieveAnalysis: getSieveAnalysisFlag(prefix) };
    }

    function buildShakerRecipeFromQuickForm() {
        var productName = (document.getElementById('quick-product-name') || {}).value || '';
        var batchNumber = (document.getElementById('quick-batch-number') || {}).value || '';
        var amplitudeRaw = parseFloat((document.getElementById('quick-amplitude') || {}).value);
        var mode = getQuickShakerMode();
        productName = productName.trim();
        batchNumber = batchNumber.trim();
        if (!productName || !batchNumber) {
            showAppModal('Please enter recipe name and batch number.', 'Quick Test');
            return null;
        }
        if (isNaN(amplitudeRaw) || amplitudeRaw < 0.5 || amplitudeRaw > 3.0) {
            showAppModal('Please enter amplitude between 0.5 and 3.0.', 'Quick Test');
            return null;
        }
        var amplitude = Math.round(amplitudeRaw * 10); // convert to backend units (5-30)
        if (!validateSieveOrder('quick')) {
            showAppModal('Sieve sizes must be in ascending order (smallest at bottom).', 'Quick Test');
            return null;
        }
        var sieveData = collectSieveData('quick');
        var weighMethod = ((document.getElementById('quick-weigh-method') || {}).value) || 'automatic';
        var recipe = {
            productName: productName,
            batchNumber: batchNumber,
            shakerMode: mode,
            amplitude: amplitude,
            numSieves: sieveData.numSieves,
            sieveSizes: sieveData.sieveSizes,
            sieveAnalysis: sieveData.sieveAnalysis !== false,
            weighMethod: weighMethod,
            quickTest: true
        };
        if (mode === 'LOGICAL') {
            var totalSec = parseMmSsToSeconds((document.getElementById('quick-logical-total-duration') || {}).value);
            var runSec   = parseMmSsToSeconds((document.getElementById('quick-logical-run-time') || {}).value);
            var waitSec  = parseMmSsToSeconds((document.getElementById('quick-logical-wait-time') || {}).value) || 0;
            if (!totalSec || totalSec < 1 || !runSec || runSec < 1) {
                showAppModal('Please enter valid Total Duration and Run Time for Logical mode.', 'Quick Test');
                return null;
            }
            var cycleSec   = runSec + waitSec;
            var numCycles  = cycleSec > 0 ? Math.floor(totalSec / cycleSec) : 0;
            if (numCycles < 1) {
                showAppModal('Total duration must be at least one full run+wait cycle.', 'Quick Test');
                return null;
            }
            var segments = [];
            for (var c = 0; c < numCycles; c++) {
                segments.push({ type: 'run', durationSeconds: runSec });
                if (waitSec > 0) segments.push({ type: 'wait', durationSeconds: waitSec });
            }
            recipe.logicalSegments = segments;
            recipe.durationSeconds = totalSec;
            recipe.logicalRunSeconds  = runSec;
            recipe.logicalWaitSeconds = waitSec;
            recipe.logicalCycles      = numCycles;
        } else {
            var durationSec = parseMmSsToSeconds((document.getElementById('quick-duration') || {}).value);
            if (durationSec == null || durationSec < 1) {
                showAppModal('Please enter a valid duration (MM:SS).', 'Quick Test');
                return null;
            }
            recipe.durationSeconds = durationSec;
            // INTERMITTENT: duration + amplitude only; hardware command uses mode letter I.
        }
        return recipe;
    }

    window.startQuickTestRunFromParams = function () {
        var recipe = buildShakerRecipeFromQuickForm();
        if (!recipe) return;
        window._quickTestRunPendingFormReset = true;
        startTestRun(recipe);
    };

    window.saveRecipeFromParams = function () {
        var productName = ((document.getElementById('recipe-product-name') || {}).value || '').trim();
        var amplitudeRaw = parseFloat((document.getElementById('recipe-amplitude') || {}).value);
        var mode = getRecipeShakerMode();
        if (!productName) {
            showAppModal('Please enter recipe name.', 'Create Recipe');
            return;
        }
        if (isNaN(amplitudeRaw) || amplitudeRaw < 0.5 || amplitudeRaw > 3.0) {
            showAppModal('Please enter amplitude between 0.5 and 3.0.', 'Create Recipe');
            return;
        }
        var amplitude = Math.round(amplitudeRaw * 10); // convert to backend units (5-30)
        if (!validateSieveOrder('recipe')) {
            showAppModal('Sieve sizes must be in ascending order (smallest at bottom).', 'Create Recipe');
            return;
        }
        var sieveData = collectSieveData('recipe');
        var weighMethod = ((document.getElementById('recipe-weigh-method') || {}).value) || 'automatic';
        var recipe = {
            productName: productName,
            shakerMode: mode,
            amplitude: amplitude,
            numSieves: sieveData.numSieves,
            sieveSizes: sieveData.sieveSizes,
            sieveAnalysis: sieveData.sieveAnalysis !== false,
            weighMethod: weighMethod,
            createdAt: (typeof formatLocalWallClockIso === 'function') ? formatLocalWallClockIso() : new Date().toISOString()
        };
        if (mode === 'LOGICAL') {
            var totalSec = parseMmSsToSeconds((document.getElementById('recipe-logical-total-duration') || {}).value);
            var runSec   = parseMmSsToSeconds((document.getElementById('recipe-logical-run-time') || {}).value);
            var waitSec  = parseMmSsToSeconds((document.getElementById('recipe-logical-wait-time') || {}).value) || 0;
            if (!totalSec || totalSec < 1 || !runSec || runSec < 1) {
                showAppModal('Please enter valid Total Duration and Run Time for Logical mode.', 'Create Recipe');
                return;
            }
            var cycleSec  = runSec + waitSec;
            var numCycles = cycleSec > 0 ? Math.floor(totalSec / cycleSec) : 0;
            if (numCycles < 1) {
                showAppModal('Total duration must be at least one full run+wait cycle.', 'Create Recipe');
                return;
            }
            var segments = [];
            for (var c = 0; c < numCycles; c++) {
                segments.push({ type: 'run', durationSeconds: runSec });
                if (waitSec > 0) segments.push({ type: 'wait', durationSeconds: waitSec });
            }
            recipe.logicalSegments    = segments;
            recipe.durationSeconds    = totalSec;
            recipe.logicalRunSeconds  = runSec;
            recipe.logicalWaitSeconds = waitSec;
            recipe.logicalCycles      = numCycles;
        } else {
            var durationSec = parseMmSsToSeconds((document.getElementById('recipe-duration') || {}).value);
            if (durationSec == null || durationSec < 1) {
                showAppModal('Please enter a valid duration (MM:SS).', 'Create Recipe');
                return;
            }
            recipe.durationSeconds = durationSec;
            // INTERMITTENT: duration + amplitude only; hardware command uses mode letter I.
        }
        var editId = window.currentEditingRecipeId;
        if (editId) recipe.id = editId;
        var url = editId ? (API_BASE + '/api/data/recipes/' + editId) : (API_BASE + '/api/data/recipes');
        var method = editId ? 'PUT' : 'POST';
        apiRequest(url, { method: method, body: recipe }).then(function (result) {
            window.currentEditingRecipeId = null;
            if (typeof recipeListMode !== 'undefined') recipeListMode = 'manage';
            goToPage('manage-recipes');
            if (typeof loadManageRecipes === 'function') loadManageRecipes();
            var rid = (result && result.id != null) ? result.id : ((result && result.recipe && result.recipe.id != null) ? result.recipe.id : null);
            if (rid != null) {
                setTimeout(function () {
                    approveSavedRecipeWithCredentials(rid, 'Save Recipe', '').then(function (res) {
                        if (res && res.cancelled) {
                            showAppModal('Recipe saved. It stays pending until a QA or Admin approves it.', 'Save Recipe');
                        }
                    });
                }, 50);
            }
        }).catch(function (err) {
            showAppModal('Failed to save recipe: ' + ((err && err.message) ? err.message : 'Unknown error'), 'Create Recipe');
        });
    };

    // ---- Test run module ----
    var _sr = {
        recipe: null,
        running: false,
        done: false,
        abortedRun: false,
        completedEarly: false,
        weighingActive: false,
        manualWeighUsed: false,
        testStartIso: null,
        livePollInterval: null,
        targetSeconds: 0,
        elapsedSeconds: 0,
        runEndElapsedSeconds: 0,
        pollStartTime: 0
    };

    function _srEl(id) { return document.getElementById(id); }

    function _wzId(containerId, name) {
        return String(containerId || 'wz') + '-' + name;
    }

    function _wzHideAndClear(containerId) {
        var el = document.getElementById(containerId);
        if (!el) return;
        el.style.display = 'none';
        el.innerHTML = '';
    }

    function _srMarkActivity() {
        if (typeof markAutoLogoutActivity === 'function') {
            try { markAutoLogoutActivity(); } catch (e) {}
        }
    }

    function _srBuildReportPayload(opts) {
        opts = opts || {};
        var recipe = _sr.recipe || {};
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var analysisOn = isSieveAnalysisOn(recipe);
        var aborted = !!(_sr.abortedRun || opts.aborted);
        var beforeWeights = _sr.beforeWeights || [];
        var afterWeights = _sr.afterWeightsByIdx || [];
        var sieveWeights = _sr.fractions || [];
        var panFraction = _sr.panFraction || 0;
        var sampleWeight = _sr.sampleWeight || 0;
        var finalWeight = analysisOn ? (_sr.totalFraction || 0) : null;
        return {
            name: 'Sieve Shaker Test - ' + (recipe.productName || 'Recipe') + (aborted ? ' (Aborted)' : ''),
            type: 'test',
            recipe: recipe,
            testData: {
                shakerMode: recipe.shakerMode,
                amplitude: recipe.amplitude,
                durationSeconds: _sr.targetSeconds,
                setDurationSeconds: _sr.targetSeconds,
                intermittentOnSeconds: recipe.intermittentOnSeconds,
                intermittentOffSeconds: recipe.intermittentOffSeconds,
                logicalSegments: recipe.logicalSegments,
                actualElapsedSeconds: Math.floor(_sr.runEndElapsedSeconds || _sr.elapsedSeconds || 0),
                elapsedSeconds: Math.floor(_sr.runEndElapsedSeconds || _sr.elapsedSeconds || 0),
                completedEarly: _sr.completedEarly,
                status: aborted ? 'Aborted' : 'Completed',
                testStatus: 'Pending',
                verdict: 'PENDING',
                result: 'PENDING',
                drumCount: 1,
                batchNumber: recipe.batchNumber,
                productName: recipe.productName,
                numSieves: numSieves,
                sieveSizes: recipe.sieveSizes || [],
                sieveAnalysis: analysisOn,
                beforeWeights: analysisOn ? beforeWeights : [],
                afterWeights: analysisOn ? afterWeights : [],
                sieveWeights: analysisOn ? sieveWeights : [],
                panWeight: analysisOn ? panFraction : 0,
                initialWeight: sampleWeight,
                finalWeight: finalWeight,
                weighMethod: getReportWeighMethod(),
                testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : '',
                testStartTime: _sr.testStartIso || null,
                testEndTime: (aborted || _sr.done) ? (typeof formatLocalWallClockIso === 'function' ? formatLocalWallClockIso() : new Date().toISOString()) : null
            }
        };
    }

    function _srWriteCheckpoint(phase) {
        try {
            var payload = _srBuildReportPayload({ aborted: false });
            var nowIso = typeof formatLocalWallClockIso === 'function' ? formatLocalWallClockIso() : new Date().toISOString();
            if (!_sr.testStartIso && (_sr.running || phase === 'running')) {
                _sr.testStartIso = nowIso;
            }
            payload._checkpointPhase = phase || (_sr.weighingActive ? 'weighing' : (_sr.running ? 'running' : 'weighing'));
            payload._checkpointAt = nowIso;
            if (payload.testData) {
                payload.testData.status = _sr.running ? 'running' : (payload.testData.status || 'running');
                payload.testData.durationSeconds = _sr.targetSeconds;
                payload.testData.setDurationSeconds = _sr.targetSeconds;
                payload.testData.actualElapsedSeconds = Math.floor(_sr.runEndElapsedSeconds || _sr.elapsedSeconds || 0);
                payload.testData.elapsedSeconds = Math.floor(_sr.runEndElapsedSeconds || _sr.elapsedSeconds || 0);
                payload.testData.testStartTime = _sr.testStartIso || payload.testData.testStartTime || nowIso;
                payload.testData.testEndTime = nowIso;
            }
            payload.createdAt = _sr.testStartIso || nowIso;
            payload.completedAt = nowIso;
            return apiRequest(API_BASE + '/api/data/test-run/checkpoint', {
                method: 'PUT',
                body: payload
            }).catch(function () { return null; });
        } catch (e) {
            return Promise.resolve(null);
        }
    }

    function _srClearCheckpoint() {
        return apiRequest(API_BASE + '/api/data/test-run/checkpoint', { method: 'DELETE' })
            .catch(function () { return null; });
    }

    function _srSavePartialReport() {
        _sr.abortedRun = true;
        stopScalePoll('wz');
        _wzOnWeight = null;
        _sr.weighingActive = false;
        if (!_sr.afterWeightsByIdx) _sr.afterWeightsByIdx = [];
        if (!_sr.fractions) _sr.fractions = [];
        var payload = _srBuildReportPayload({ aborted: true });
        return apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: payload })
            .then(function (res) {
                return _srClearCheckpoint().then(function () { return res; });
            })
            .catch(function () { return null; });
    }

    function _srTargetSeconds(recipe) {
        if (!recipe) return 0;
        if (String(recipe.shakerMode || '').toUpperCase() === 'LOGICAL') {
            return computeLogicalTotalSeconds(recipe.logicalSegments || []);
        }
        return parseInt(recipe.durationSeconds, 10) || 0;
    }

    window.initTestRunPage = function (recipe) {
        _sr.recipe = recipe || {};
        if (_sr.recipe.sieveAnalysis === undefined || _sr.recipe.sieveAnalysis === null) {
            _sr.recipe.sieveAnalysis = true;
        } else {
            _sr.recipe.sieveAnalysis = isSieveAnalysisOn(_sr.recipe);
        }
        _sr.running = false;
        _sr.done = false;
        _sr.abortedRun = false;
        _sr.completedEarly = false;
        _sr.weighingActive = false;
        _sr.manualWeighUsed = false;
        _sr.testStartIso = null;
        _sr.targetSeconds = _srTargetSeconds(_sr.recipe);
        _sr.elapsedSeconds = 0;
        _sr.runEndElapsedSeconds = 0;
        if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }

        if (_srEl('tr-product-name')) _srEl('tr-product-name').textContent = recipe.productName || recipe.name || '--';
        if (_srEl('tr-batch-number')) _srEl('tr-batch-number').textContent = recipe.batchNumber || '--';
        if (_srEl('tr-mode')) _srEl('tr-mode').textContent = shakerModeLabel(recipe.shakerMode);
        if (_srEl('tr-amplitude')) {
            _srEl('tr-amplitude').textContent = (typeof formatAmplitudeDisplay === 'function')
                ? formatAmplitudeDisplay(recipe.amplitude)
                : (recipe.amplitude != null ? (recipe.amplitude / 10).toFixed(1) : '--');
        }
        if (_srEl('tr-target-duration')) _srEl('tr-target-duration').textContent = formatSecondsToMmSs(_sr.targetSeconds);
        if (_srEl('tr-phase')) _srEl('tr-phase').textContent = 'Off';
        if (_srEl('tr-set-time')) _srEl('tr-set-time').textContent = formatSecondsToMmSs(_sr.targetSeconds);
        if (_srEl('tr-timer-right')) _srEl('tr-timer-right').textContent = '00:00';
        if (_srEl('tr-segment-info')) _srEl('tr-segment-info').textContent = '';
        if (_srEl('tr-progress-fill')) _srEl('tr-progress-fill').style.width = '0%';
        if (_srEl('tr-progress-text')) _srEl('tr-progress-text').textContent = '0%';
        if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Press Start to begin the shaker program.';
        var swSection = document.getElementById('tr-sieve-weight-section');
        if (swSection) swSection.style.display = 'none';
        var runScreen = document.getElementById('tr-run-screen');
        if (runScreen) runScreen.style.display = '';
        var weightSection = document.getElementById('tr-weight-section');
        if (weightSection) weightSection.style.display = '';
        _srSetButtons('idle');
        // Set up SVG sieve layers and sieve count label
        _srSetSieveSvg(recipe);
        // Hide and clear wizards (avoid leftover duplicate IDs)
        _wzHideAndClear('tr-before-wizard');
        _wzHideAndClear('tr-after-wizard');
        _sr.weighingActive = false;
    };

    function _srSetSieveSvg(recipe) {
        var n = parseInt((recipe || {}).numSieves, 10) || 0;
        // Show/hide sieve layers 1-8
        for (var i = 1; i <= 8; i++) {
            var el = document.getElementById('tr-sieve-layer-' + i);
            if (el) el.setAttribute('display', i <= n ? '' : 'none');
        }
        // Update sieve count label
        var lbl = document.getElementById('tr-sieve-count-label');
        if (lbl) lbl.textContent = n + ' sieve' + (n !== 1 ? 's' : '') + ' + PAN';
        // Also sync right-column timer displays
        var td = document.getElementById('tr-timer-right');
        if (td) td.textContent = '00:00';
    }

    function _srSetAnimating(on) {
        var svg = document.getElementById('tr-sieve-svg');
        if (!svg) return;
        if (on) svg.classList.add('shaker-animating');
        else svg.classList.remove('shaker-animating');
    }

    function _srSetButtons(state) {
        var start = _srEl('tr-start-btn');
        var stop = _srEl('tr-stop-btn');
        var statusPill = document.getElementById('tr-status-label');
        if (!start || !stop) return;
        if (state === 'idle') {
            start.style.display = '';
            start.disabled = false;
            start.textContent = 'START';
            stop.disabled = false;
            if (statusPill) {
                statusPill.textContent = 'IDLE';
                statusPill.className = 'tr-status-pill';
            }
        } else if (state === 'running') {
            start.style.display = 'none';
            stop.disabled = false;
            if (statusPill) {
                statusPill.textContent = 'TEST RUNNING';
                statusPill.className = 'tr-status-pill status-running';
            }
        } else if (state === 'done') {
            start.style.display = 'none';
            stop.disabled = true;
            if (statusPill) {
                statusPill.textContent = 'COMPLETED';
                statusPill.className = 'tr-status-pill status-done';
            }
        }
    }

    function _srRefreshFromLive(data) {
        if (!data) return;
        var phase = String(data.phase || 'off');
        var elapsed = parseFloat(data.elapsedSec);
        if (isNaN(elapsed)) elapsed = 0;
        if (_sr.running && !data.programDone) {
            var localElapsed = _sr.pollStartTime ? ((Date.now() - _sr.pollStartTime) / 1000) : 0;
            elapsed = Math.max(elapsed, _sr.elapsedSeconds || 0, localElapsed);
        }
        _sr.elapsedSeconds = elapsed;
        var target = parseInt(data.targetDurationSec, 10) || _sr.targetSeconds || 1;
        var remaining = Math.max(0, target - elapsed);
        var elapsedStr = formatSecondsToMmSs(Math.floor(elapsed));
        if (_srEl('tr-timer-right')) _srEl('tr-timer-right').textContent = elapsedStr;
        if (_srEl('tr-phase')) _srEl('tr-phase').textContent = phase.charAt(0).toUpperCase() + phase.slice(1);
        var pct = Math.min(100, (elapsed / Math.max(1, target)) * 100);
        if (_srEl('tr-progress-fill')) _srEl('tr-progress-fill').style.width = pct.toFixed(1) + '%';
        if (_srEl('tr-progress-text')) _srEl('tr-progress-text').textContent = pct.toFixed(0) + '%';
        var segIdx = parseInt(data.segmentIndex, 10) || 0;
        var segCount = parseInt(data.segmentCount, 10) || 0;
        if (_srEl('tr-segment-info') && segCount > 0) {
            _srEl('tr-segment-info').textContent = 'Segment ' + segIdx + ' of ' + segCount;
        }
        var icon = _srEl('tr-shaker-icon');
        if (icon) icon.classList.toggle('shaker-active', phase === 'run');
        _srSetAnimating(phase === 'run');

        var modeBadge = _srEl('tr-hw-mode-badge');
        if (modeBadge) {
            var hwMode = String(data.mode || 'C').toUpperCase();
            modeBadge.textContent = hwMode;
            modeBadge.className = 'hw-mode-badge' + (phase === 'run' ? (hwMode === 'I' ? ' badge-intermittent' : ' badge-continuous') : ' badge-off');
        }
    }

    function _srPollLive() {
        return apiRequest(API_BASE + '/api/hardware/shaker/live', { method: 'GET' }).then(function (data) {
            _srRefreshFromLive(data);
            if (data && data.programDone && _sr.running) {
                _sr.runEndElapsedSeconds = _srCaptureRunElapsed();
                _sr.elapsedSeconds = _sr.runEndElapsedSeconds;
                _srFinishRun(false);
            }
            return data;
        }).catch(function () { return null; });
    }

    function _srStartPoll() {
        if (_sr.livePollInterval) clearInterval(_sr.livePollInterval);
        _sr.elapsedSeconds = 0;
        _sr.pollStartTime = Date.now();
        _sr.livePollInterval = setInterval(function () {
            var localElapsed = (Date.now() - _sr.pollStartTime) / 1000;
            _sr.elapsedSeconds = Math.max(_sr.elapsedSeconds || 0, localElapsed);
            var elapsedStr = formatSecondsToMmSs(Math.floor(localElapsed));
            if (_srEl('tr-timer-right')) _srEl('tr-timer-right').textContent = elapsedStr;
            var pct = Math.min(100, (localElapsed / Math.max(1, _sr.targetSeconds)) * 100);
            if (_srEl('tr-progress-fill')) _srEl('tr-progress-fill').style.width = pct.toFixed(1) + '%';
            if (_srEl('tr-progress-text')) _srEl('tr-progress-text').textContent = pct.toFixed(0) + '%';
            _srPollLive();
            if (_sr.running && _sr.testStartIso) _srWriteCheckpoint('running');
        }, 1000);
    }

    function _srStopPoll() {
        if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }
    }

    function _srAuditStarted(recipe) {
        var isQuick = !!(recipe && recipe.quickTest);
        var action = isQuick ? 'Quick test started' : 'Test started';
        var details = (recipe.productName || 'Test') + ', ' + shakerModeLabel(recipe.shakerMode) +
            ', amp ' + recipe.amplitude + ', ' + formatSecondsToMmSs(_srTargetSeconds(recipe));
        logAuditEvent(action, details, { eventType: 'lifecycle', entityType: 'test', entityName: recipe.productName || '' });
    }

    function _showAbortedChoiceModal(callback) {
        var overlay = document.getElementById('app-modal-overlay');
        var titleEl = document.getElementById('app-modal-title');
        var msgEl = document.getElementById('app-modal-message');
        var buttonsEl = document.getElementById('app-modal-buttons');
        if (!overlay || !buttonsEl) { callback(true); return; }
        if (titleEl) titleEl.textContent = 'Test Aborted';
        if (msgEl) msgEl.textContent = 'The test was aborted. Would you like to weigh the sieves for a partial report, or skip weighing and save the aborted report now?';
        buttonsEl.innerHTML = '';
        var skipBtn = document.createElement('button');
        skipBtn.type = 'button';
        skipBtn.className = 'btn-role-select btn-confirm-cancel';
        skipBtn.textContent = 'Skip & Save Report';
        skipBtn.onclick = function () { overlay.style.display = 'none'; callback(false); };
        var weighBtn = document.createElement('button');
        weighBtn.type = 'button';
        weighBtn.className = 'btn-role-select btn-confirm-ok';
        weighBtn.textContent = 'Weigh Sieves';
        weighBtn.onclick = function () { overlay.style.display = 'none'; callback(true); };
        buttonsEl.appendChild(skipBtn);
        buttonsEl.appendChild(weighBtn);
        overlay.style.display = 'flex';
    }

    function _srFinishRun(aborted) {
        if (!_sr.runEndElapsedSeconds) {
            _sr.runEndElapsedSeconds = _srCaptureRunElapsed();
        }
        _sr.elapsedSeconds = _sr.runEndElapsedSeconds;
        _sr.running = false;
        _sr.done = true;
        _sr.abortedRun = !!aborted;
        _srStopPoll();
        _srSetAnimating(false);
        _srSetButtons('done');
        if (_srEl('tr-footer-note')) {
            _srEl('tr-footer-note').textContent = aborted ? 'Test aborted.' : 'Test complete.';
        }
        var recipe = _sr.recipe || {};
        var analysisOn = isSieveAnalysisOn(recipe);
        // Analysis OFF: sample already weighed before start — skip after wizard entirely.
        if (!analysisOn) {
            _sr.afterWeightsByIdx = [];
            _sr.fractions = [];
            _sr.panFraction = 0;
            _sr.finalSampleWeight = _sr.sampleWeight || 0;
            _sr.totalFraction = _sr.finalSampleWeight;
            if (typeof submitSieveWeights === 'function') submitSieveWeights();
            return;
        }
        if (aborted) {
            // Custom two-button modal: Weigh Sieves  /  Skip & Save Report
            _showAbortedChoiceModal(function (doWeigh) {
                if (doWeigh) {
                    _startAfterWizard();
                } else {
                    _sr.afterWeightsByIdx = [];
                    _sr.fractions = [];
                    _sr.panFraction = 0;
                    _sr.totalFraction = 0;
                    if (typeof submitSieveWeights === 'function') submitSieveWeights();
                }
            });
        } else {
            _startAfterWizard();
        }
    }

    // ===== WIZARD RENDER HELPER (IDs scoped per container) =====
    function _wzRenderStep(containerId, stepIdx, totalSteps, label, instruction, opts) {
        opts = opts || {};
        var el = document.getElementById(containerId);
        if (!el) return;
        var isManual = !!opts.isManual;
        var dots = '';
        for (var i = 0; i < totalSteps; i++) {
            var cls = i < stepIdx ? 'wz-dot done' : (i === stepIdx ? 'wz-dot active' : 'wz-dot');
            dots += '<span class="' + cls + '"></span>';
        }
        var isAfterWiz = containerId === 'tr-after-wizard';
        var idWeight = _wzId(containerId, 'wz-weight-val');
        var idRow = _wzId(containerId, 'wz-manual-row');
        var idInput = _wzId(containerId, 'wz-manual-input');
        var idConfirm = _wzId(containerId, 'wz-manual-confirm');
        var idBack = _wzId(containerId, 'wz-back-btn');
        var idType = _wzId(containerId, 'wz-type-btn');
        var idNext = _wzId(containerId, 'wz-next-btn');
        var idSkip = _wzId(containerId, 'wz-skip-btn');
        el.innerHTML =
            '<div class="wz-step-indicator">Step ' + (stepIdx + 1) + ' of ' + totalSteps + '</div>' +
            '<div class="wz-dots">' + dots + '</div>' +
            '<div class="wz-label">' + label + '</div>' +
            '<div class="wz-instruction">' + instruction + '</div>' +
            '<div class="wz-weight-display" id="' + idWeight + '">' + (isManual ? 'Manual Entry' : 'Waiting\u2026') + '</div>' +
            '<div class="wz-manual-row" id="' + idRow + '" style="display:' + (isManual ? 'flex' : 'none') + ';">' +
            '<input type="text" id="' + idInput + '" class="wz-manual-input decimal-input" inputmode="decimal" data-decimal-input="true" autocomplete="off" placeholder="Type weight (g) e.g. 23.1234">' +
            '<button class="wz-btn wz-btn-next" id="' + idConfirm + '" style="padding:10px 20px;">OK</button></div>' +
            '<div class="wz-buttons">' +
            (stepIdx > 0 ? '<button class="wz-btn wz-btn-back" id="' + idBack + '">Back</button>' : '') +
            (isManual ? '' : '<button class="wz-btn" style="background:#64748b;color:#fff;" id="' + idType + '">Type Manually</button>') +
            '<button class="wz-btn wz-btn-next" id="' + idNext + '" disabled>Next</button>' +
            '</div>' +
            (isAfterWiz ? '<div style="text-align:center;margin-top:10px;"><button class="wz-btn" style="background:#475569;color:#cbd5e1;font-size:13px;padding:8px 18px;" id="' + idSkip + '">Skip &amp; Save Report</button></div>' : '');
    }

    function isSieveAnalysisOn(recipe) {
        if (!recipe || recipe.sieveAnalysis === undefined || recipe.sieveAnalysis === null) return true;
        if (typeof recipe.sieveAnalysis === 'boolean') return recipe.sieveAnalysis;
        var s = String(recipe.sieveAnalysis).trim().toLowerCase();
        return !(s === '0' || s === 'false' || s === 'off' || s === 'no');
    }

    // ===== BEFORE-TEST WIZARD =====
    function _startBeforeWizard(recipe, onComplete) {
        var analysisOn = isSieveAnalysisOn(recipe);
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var sieveSizes = recipe.sieveSizes || [];
        var steps = [];
        var autoInstr = 'Place item on scale and wait for reading';
        var sampleInstr = 'Place sample on scale and wait for reading';
        if (analysisOn) {
            for (var i = 0; i < numSieves; i++) {
                steps.push({ label: 'Sieve ' + (i + 1) + ' (' + (sieveSizes[i] || '?') + ' \u00b5m)', instruction: autoInstr });
            }
            steps.unshift({ label: 'PAN (Receiver)', instruction: autoInstr });
            steps.push({ label: 'Sample', instruction: sampleInstr });
        } else {
            steps.push({ label: 'Sample weight', instruction: sampleInstr });
        }

        var weights = [];
        var currentStep = 0;
        var cid = 'tr-before-wizard';
        var container = document.getElementById(cid);
        var runScreen = document.getElementById('tr-run-screen');
        if (runScreen) runScreen.style.display = 'none';
        _wzHideAndClear('tr-after-wizard');
        if (container) container.style.display = 'flex';
        _sr.weighingActive = true;
        _srMarkActivity();
        _srWriteCheckpoint('weighing');

        function el(name) { return document.getElementById(_wzId(cid, name)); }

        function renderCurrent() {
            var isManual = getWeighMethod() === 'manual';
            if (isManual) _sr.manualWeighUsed = true;
            var instr = isManual ? 'Type the weight manually below' : (steps[currentStep].instruction);
            _wzRenderStep(cid, currentStep, steps.length, steps[currentStep].label, instr, { isManual: isManual });
            var nextBtn = el('wz-next-btn');
            var backBtn = el('wz-back-btn');
            var typeBtn = el('wz-type-btn');
            if (nextBtn) nextBtn.onclick = goNext;
            if (backBtn) backBtn.onclick = goBack;
            if (typeBtn) typeBtn.onclick = showManualInput;
            if (isManual) {
                showManualInput();
            } else {
                _wzOnWeight = function (w) {
                    var display = el('wz-weight-val');
                    if (display) { display.textContent = w.toFixed(3) + ' g'; display.classList.add('captured'); }
                    weights[currentStep] = w;
                    var nb = el('wz-next-btn');
                    if (nb) nb.disabled = false;
                    stopScalePoll('wz');
                    _srMarkActivity();
                };
                startScalePoll('wz');
            }
        }

        function showManualInput() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            _sr.manualWeighUsed = true;
            var typeBtn = el('wz-type-btn');
            if (typeBtn) typeBtn.style.display = 'none';
            var row = el('wz-manual-row');
            if (row) row.style.display = 'flex';
            var display = el('wz-weight-val');
            if (display) display.textContent = 'Manual Entry';
            var inp = el('wz-manual-input');
            if (inp) {
                inp.classList.add('decimal-input');
                inp.setAttribute('inputmode', 'decimal');
                inp.setAttribute('data-decimal-input', 'true');
                if (typeof attachInputFocusHandlers === 'function') attachInputFocusHandlers(row);
                setTimeout(function () {
                    inp.focus();
                    if (typeof openOSKForInput === 'function') {
                        try { openOSKForInput(inp); } catch (e1) {}
                    } else if (typeof showOSK === 'function') {
                        try { showOSK(inp); } catch (e2) {}
                    }
                }, 80);
            }
            var confirmBtn = el('wz-manual-confirm');
            if (confirmBtn) confirmBtn.onclick = function () {
                var v = inp ? _wzParseManualWeight(inp.value) : null;
                if (v == null) return;
                weights[currentStep] = v;
                if (display) { display.textContent = v.toFixed(4) + ' g'; display.classList.add('captured'); }
                var nb = el('wz-next-btn');
                if (nb) nb.disabled = false;
                if (row) row.style.display = 'none';
                _srMarkActivity();
            };
        }

        function goNext() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            currentStep++;
            if (currentStep >= steps.length) {
                _wzHideAndClear(cid);
                _sr.weighingActive = false;
                onComplete(weights);
                return;
            }
            renderCurrent();
        }

        function goBack() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            if (currentStep > 0) { currentStep--; weights.length = currentStep; }
            renderCurrent();
        }

        renderCurrent();
    }

    // ===== AFTER-TEST WIZARD =====
    function _startAfterWizard() {
        var recipe = _sr.recipe || {};
        var analysisOn = isSieveAnalysisOn(recipe);
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var sieveSizes = recipe.sieveSizes || [];
        var steps = [];
        if (analysisOn) {
            for (var i = numSieves - 1; i >= 0; i--) {
                steps.push({ label: 'Sieve ' + (i + 1) + ' (' + (sieveSizes[i] || '?') + ' \u00b5m)', idx: i });
            }
            steps.push({ label: 'PAN (Receiver)', idx: -1 });
        } else {
            steps.push({ label: 'Sample (final)', idx: 'final' });
        }

        var afterWeights = [];
        var currentStep = 0;
        var cid = 'tr-after-wizard';
        var container = document.getElementById(cid);
        var runScreen = document.getElementById('tr-run-screen');
        if (runScreen) runScreen.style.display = 'none';
        _wzHideAndClear('tr-before-wizard');
        if (container) container.style.display = 'flex';
        _sr.weighingActive = true;
        _srMarkActivity();
        _srWriteCheckpoint('weighing');

        function el(name) { return document.getElementById(_wzId(cid, name)); }

        function renderCurrent() {
            var isManual = getWeighMethod() === 'manual';
            var instr = isManual ? 'Type the weight manually below' : 'Place sieve with powder on scale and wait for reading';
            _wzRenderStep(cid, currentStep, steps.length, steps[currentStep].label, instr, { isManual: isManual });
            var nextBtn = el('wz-next-btn');
            var backBtn = el('wz-back-btn');
            var typeBtn = el('wz-type-btn');
            if (nextBtn) nextBtn.onclick = goNext;
            if (backBtn) backBtn.onclick = goBack;
            if (typeBtn) typeBtn.onclick = showManualInput;
            var skipBtn = el('wz-skip-btn');
            if (skipBtn) skipBtn.onclick = skipAndSaveReport;
            if (isManual) {
                showManualInput();
            } else {
                _wzOnWeight = function (w) {
                    var display = el('wz-weight-val');
                    if (display) { display.textContent = w.toFixed(3) + ' g'; display.classList.add('captured'); }
                    afterWeights[currentStep] = w;
                    var nb = el('wz-next-btn');
                    if (nb) nb.disabled = false;
                    stopScalePoll('wz');
                    _srMarkActivity();
                };
                startScalePoll('wz');
            }
        }

        function skipAndSaveReport() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            _wzHideAndClear(cid);
            _sr.weighingActive = false;
            _sr.afterWeightsByIdx = [];
            _sr.fractions = [];
            _sr.panFraction = 0;
            _sr.totalFraction = 0;
            if (typeof submitSieveWeights === 'function') submitSieveWeights();
        }

        function showManualInput() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            _sr.manualWeighUsed = true;
            var typeBtn = el('wz-type-btn');
            if (typeBtn) typeBtn.style.display = 'none';
            var row = el('wz-manual-row');
            if (row) row.style.display = 'flex';
            var display = el('wz-weight-val');
            if (display) display.textContent = 'Manual Entry';
            var inp = el('wz-manual-input');
            if (inp) {
                inp.classList.add('decimal-input');
                inp.setAttribute('inputmode', 'decimal');
                inp.setAttribute('data-decimal-input', 'true');
                if (typeof attachInputFocusHandlers === 'function') attachInputFocusHandlers(row);
                setTimeout(function () {
                    inp.focus();
                    if (typeof openOSKForInput === 'function') {
                        try { openOSKForInput(inp); } catch (e1) {}
                    }
                }, 80);
            }
            var confirmBtn = el('wz-manual-confirm');
            if (confirmBtn) confirmBtn.onclick = function () {
                var v = inp ? _wzParseManualWeight(inp.value) : null;
                if (v == null) return;
                afterWeights[currentStep] = v;
                if (display) { display.textContent = v.toFixed(4) + ' g'; display.classList.add('captured'); }
                var nb = el('wz-next-btn');
                if (nb) nb.disabled = false;
                if (row) row.style.display = 'none';
                _srMarkActivity();
            };
        }

        function goNext() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            currentStep++;
            if (currentStep >= steps.length) {
                showSummary();
                return;
            }
            renderCurrent();
        }

        function goBack() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            if (currentStep > 0) { currentStep--; afterWeights.length = currentStep; }
            renderCurrent();
        }

        function showSummary() {
            if (!analysisOn) {
                var finalW = afterWeights[0] || 0;
                _sr.afterWeightsByIdx = [];
                _sr.fractions = [];
                _sr.panFraction = 0;
                _sr.totalFraction = finalW;
                _sr.finalSampleWeight = finalW;
                container.innerHTML =
                    '<div class="wz-summary">' +
                    '<div class="wz-summary-title">Weight Summary</div>' +
                    '<div style="font-size:15px;color:#e2e8f0;margin:12px 0;">Initial Sample: ' + (_sr.sampleWeight || 0).toFixed(3) + ' g</div>' +
                    '<div style="font-size:15px;color:#e2e8f0;margin:12px 0;">Final Sample: ' + finalW.toFixed(3) + ' g</div>' +
                    '<div style="font-size:13px;color:#94a3b8;">Sieve analysis was OFF for this test.</div>' +
                    '<div class="wz-verdict-row">' +
                    '<button class="wz-btn wz-btn-start" style="width:100%;font-size:1.1rem;" onclick="submitSieveWeights()">Save &amp; View Report</button>' +
                    '</div></div>';
                return;
            }
            var afterByIdx = [];
            for (var j = 0; j < steps.length; j++) {
                var s = steps[j];
                if (s.idx === -1) { afterByIdx[numSieves] = afterWeights[j]; }
                else { afterByIdx[s.idx] = afterWeights[j]; }
            }
            var beforeWeights = _sr.beforeWeights || [];
            var rows = '';
            var totalFraction = 0;
            for (var i = 0; i < numSieves; i++) {
                var bw = beforeWeights[i] || 0;
                var aw = afterByIdx[i] || 0;
                var frac = aw - bw;
                totalFraction += frac;
                rows += '<tr><td>' + (i + 1) + '</td><td>' + (sieveSizes[i] || '--') + '</td><td>' + bw.toFixed(3) + '</td><td>' + aw.toFixed(3) + '</td><td>' + frac.toFixed(3) + '</td></tr>';
            }
            var panBefore = beforeWeights[numSieves] || 0;
            var panAfter = afterByIdx[numSieves] || 0;
            var panFrac = panAfter - panBefore;
            totalFraction += panFrac;
            rows += '<tr><td>PAN</td><td>Receiver</td><td>' + panBefore.toFixed(3) + '</td><td>' + panAfter.toFixed(3) + '</td><td>' + panFrac.toFixed(3) + '</td></tr>';
            rows += '<tr class="wz-summary-total"><td colspan="4">Total Fraction</td><td>' + totalFraction.toFixed(3) + '</td></tr>';

            container.innerHTML =
                '<div class="wz-summary">' +
                '<div class="wz-summary-title">Weight Summary</div>' +
                '<table class="wz-summary-table"><thead><tr><th>Sieve</th><th>\u00b5m</th><th>Before (g)</th><th>After (g)</th><th>Fraction (g)</th></tr></thead><tbody>' + rows + '</tbody></table>' +
                '<div style="font-size:13px;color:#94a3b8;">Sample Weight: ' + (_sr.sampleWeight || 0).toFixed(3) + ' g</div>' +
                '<div class="wz-verdict-row">' +
                '<button class="wz-btn wz-btn-start" style="width:100%;font-size:1.1rem;" onclick="submitSieveWeights()">Save &amp; View Report</button>' +
                '</div></div>';

            _sr.afterWeightsByIdx = afterByIdx;
            _sr.fractions = [];
            for (var k = 0; k < numSieves; k++) {
                _sr.fractions.push((afterByIdx[k] || 0) - (beforeWeights[k] || 0));
            }
            _sr.panFraction = panFrac;
            _sr.totalFraction = totalFraction;
        }

        renderCurrent();
    }

    window.submitSieveWeights = function () {
        stopScalePoll('wz');
        _wzOnWeight = null;
        _sr.weighingActive = false;
        _wzHideAndClear('tr-before-wizard');
        _wzHideAndClear('tr-after-wizard');
        var payload = _srBuildReportPayload({ aborted: !!_sr.abortedRun });
        return apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: payload }).then(function (res) {
            var reportId = res && (res.id != null ? res.id : (res.report && res.report.id));
            if (typeof logAuditEvent === 'function') {
                logAuditEvent('Test finished', 'Sieve shaker test saved | report id ' + (reportId != null ? reportId : '--') + (_sr.abortedRun ? ' (Aborted)' : ''), {
                    eventType: 'lifecycle', entityType: 'report', entityId: reportId != null ? String(reportId) : ''
                });
            }
            return _srClearCheckpoint().then(function () {
                if (typeof finishTestRunReportSaved === 'function') {
                    finishTestRunReportSaved(reportId);
                } else if (reportId != null && typeof openReportPreview === 'function') {
                    openReportPreview(reportId, { setGate: true });
                } else {
                    goToPage('reports');
                }
                return res;
            });
        }).catch(function () {
            showAppModal('Failed to save report.', 'Test Run');
        });
    };

    window.trHandleStartButton = function () {
        if (_sr.running || _sr.done) return;
        var recipe = _sr.recipe || {};
        // Start before-test weight wizard
        _startBeforeWizard(recipe, function (weights) {
            var analysisOn = isSieveAnalysisOn(recipe);
            var numSieves = parseInt(recipe.numSieves, 10) || 0;
            if (analysisOn) {
                // weights: [PAN, sieve1..N, sample]
                _sr.beforeWeights = []; // index 0..N-1 = sieves, index N = PAN
                for (var wi = 0; wi < numSieves; wi++) { _sr.beforeWeights.push(weights[wi + 1] || 0); }
                _sr.beforeWeights.push(weights[0] || 0); // PAN at end
                _sr.sampleWeight = weights[numSieves + 1] || 0;
            } else {
                // weights: [sample]
                _sr.beforeWeights = [];
                _sr.sampleWeight = weights[0] || 0;
            }
            // Now start the actual hardware program
            var runScreen = document.getElementById('tr-run-screen');
            if (runScreen) runScreen.style.display = '';
            // Start timer immediately so elapsed time runs regardless of API latency
            _sr.running = true;
            _sr.weighingActive = false;
            _srSetButtons('running');
            if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Test Running\u2026';
            _srStartPoll();
            apiRequest(API_BASE + '/api/hardware/shaker/run-program', { method: 'POST', body: recipe })
                .then(function (res) {
                    if (!res || !res.ok) {
                        // Stop timer and revert on hard failure
                        _sr.running = false;
                        if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }
                        _srSetButtons('idle');
                        if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Press Start to begin the shaker program.';
                        _srClearCheckpoint();
                        showAppModal((res && res.error) ? String(res.error) : 'Failed to start shaker program.', 'Test Run');
                        return;
                    }
                    _sr.testStartIso = typeof formatLocalWallClockIso === 'function' ? formatLocalWallClockIso() : new Date().toISOString();
                    _srWriteCheckpoint('running');
                    _srAuditStarted(recipe);
                })
                .catch(function (err) {
                    _sr.running = false;
                    if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }
                    _srSetButtons('idle');
                    if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Press Start to begin the shaker program.';
                    _srClearCheckpoint();
                    showAppModal('Failed to start: ' + (err && err.message ? err.message : 'Error'), 'Test Run');
                });
        });
    };

    window.trCompleteTest = function () {
        if (!_sr.running) return;
        _sr.completedEarly = true;
        apiRequest(API_BASE + '/api/hardware/shaker/complete', { method: 'POST', body: {} })
            .then(function () { return _srPollLive(); })
            .then(function () { _srFinishRun(false); });
    };

    window.trStopTest = function () {
        if (!_sr.running && !_sr.done) {
            if (typeof goToPage === 'function') goToPage('home');
            return;
        }
        if (_sr.done) return;
        showConfirmModal('Abort this test run?', 'Test Run').then(function (ok) {
            if (!ok) return;
            logAuditEvent('Test aborted', 'User aborted shaker test', { eventType: 'lifecycle', outcome: 'aborted' });
            apiRequest(API_BASE + '/api/hardware/shaker/abort', { method: 'POST', body: {} })
                .then(function () { _srFinishRun(true); });
        });
    };

    window.trInitialize = function () { window.trHandleStartButton(); };
    window.trStartTest = function () { window.trHandleStartButton(); };
    window.trPauseTest = function () {};
    window.trResumeTest = function () {};
    window.trDispenseTest = function () {};

    var origLoadRecipeForEdit = window.loadRecipeForEdit;
    window.loadRecipeForEdit = function () {
        var id = window.currentEditingRecipeId;
        if (!id) return;
        apiRequest(API_BASE + '/api/data/recipes/' + id).then(function (data) {
            var r = data.recipe || data;
            if (!r) return;
            var nameEl = document.getElementById('recipe-product-name');
            if (nameEl) nameEl.value = r.productName || r.name || '';
            var mode = String(r.shakerMode || 'CONTINUOUS').toUpperCase();
            var modeRadio = document.querySelector('input[name="recipe-shaker-mode"][value="' + mode + '"]');
            if (modeRadio) modeRadio.checked = true;
            var ampEl = document.getElementById('recipe-amplitude');
            if (ampEl && r.amplitude != null) ampEl.value = String((r.amplitude / 10).toFixed(1)); // convert backend (5-30) → display (0.5-3.0)
            if (mode === 'LOGICAL') {
                window._recipeLogicalSegments = (r.logicalSegments || []).map(function (s) {
                    return {
                        type: s.type,
                        durationSeconds: s.durationSeconds,
                        duration: formatSecondsToMmSs(s.durationSeconds)
                    };
                });
            }
            applyRecipeShakerModeToFields();
            if (r.durationSeconds != null) {
                var durEl = document.getElementById('recipe-duration');
                if (durEl) durEl.value = formatSecondsToMmSs(parseInt(r.durationSeconds, 10));
            }
            if (r.intermittentOnSeconds != null) {
                var onEl = document.getElementById('recipe-on-time');
                if (onEl) onEl.value = formatSecondsToMmSs(parseInt(r.intermittentOnSeconds, 10));
            }
            if (r.intermittentOffSeconds != null) {
                var offEl = document.getElementById('recipe-off-time');
                if (offEl) offEl.value = formatSecondsToMmSs(parseInt(r.intermittentOffSeconds, 10));
            }
            // Restore sieve count + sizes (edit must not silently fall back to 5).
            var nSieves = parseInt(r.numSieves, 10);
            if (isNaN(nSieves) || nSieves < 1) {
                nSieves = Array.isArray(r.sieveSizes) ? r.sieveSizes.length : 1;
            }
            nSieves = Math.max(1, Math.min(8, nSieves));
            var numEl = document.getElementById('recipe-num-sieves');
            if (numEl) numEl.value = String(nSieves);
            if (typeof renderSieveSizeFields === 'function') renderSieveSizeFields('recipe');
            var sizes = Array.isArray(r.sieveSizes) ? r.sieveSizes : [];
            for (var si = 0; si < nSieves; si++) {
                var micron = parseInt(sizes[si], 10);
                if (isNaN(micron) || micron <= 0) continue;
                var mesh = '';
                for (var aj = 0; aj < ASTM_SIEVES.length; aj++) {
                    if (ASTM_SIEVES[aj].micron === micron) { mesh = ASTM_SIEVES[aj].mesh; break; }
                }
                var btn = document.getElementById('recipe-sieve-size-' + (si + 1));
                var hidden = document.getElementById('recipe-sieve-val-' + (si + 1));
                if (btn) {
                    btn.innerHTML = '<span class="mb-mesh">' + (mesh || ('#' + micron)) + '</span>' +
                        '<span class="mb-micron">' + micron + ' \u00b5m</span>';
                    btn.dataset.value = String(micron);
                    btn.classList.add('selected');
                }
                if (hidden) hidden.value = String(micron);
            }
            if (typeof validateSieveOrder === 'function') validateSieveOrder('recipe');
            setSieveAnalysisFlag('recipe', r.sieveAnalysis !== false);
            var wmEl = document.getElementById('recipe-weigh-method');
            if (wmEl && r.weighMethod) wmEl.value = String(r.weighMethod);
            if (mode === 'LOGICAL') {
                // Restore fields from saved logicalRunSeconds / logicalWaitSeconds / durationSeconds
                var loadRunSec  = r.logicalRunSeconds  || 0;
                var loadWaitSec = r.logicalWaitSeconds || 0;
                var loadTotSec  = r.durationSeconds    || 0;
                var elTot  = document.getElementById('recipe-logical-total-duration');
                var elRun  = document.getElementById('recipe-logical-run-time');
                var elWait = document.getElementById('recipe-logical-wait-time');
                if (elTot  && loadTotSec)  elTot.value  = formatSecondsToMmSs(loadTotSec);
                if (elRun  && loadRunSec)  elRun.value  = formatSecondsToMmSs(loadRunSec);
                if (elWait && loadWaitSec) elWait.value = formatSecondsToMmSs(loadWaitSec);
                updateLogicalCycles('recipe');
            }
        }).catch(function () {});
    };

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof applyQuickShakerModeToFields === 'function') applyQuickShakerModeToFields();
    });

    window._finalizeRecipeLoad = function (recipe, ctx) {
        var resolvedCtx = ctx || {};
        recipe.batchNumber = resolvedCtx.batchNumber1 || resolvedCtx.batchNumber || '--';
        if (recipe.sieveAnalysis === undefined || recipe.sieveAnalysis === null) {
            recipe.sieveAnalysis = true;
        } else {
            recipe.sieveAnalysis = isSieveAnalysisOn(recipe);
        }
        pendingRecipeLoadContext = null;
        pendingRecipeToLoad = null;
        logAuditEvent('Loaded recipe', (recipe.productName || 'Recipe') + ', batch ' + (recipe.batchNumber || '--'), {
            eventType: 'lifecycle'
        });
        startTestRun(recipe);
    };

    window.confirmBatchNumberAndLoad = function () {
        var input = document.getElementById('load-recipe-batch-input');
        var batch = input ? input.value.trim() : '';
        if (!pendingRecipeToLoad) {
            closeBatchNumberModal();
            return;
        }
        if (getEffectiveRecipeApprovalStatus(pendingRecipeToLoad) === 'pending') {
            showAppModal('This recipe is pending QA approval and cannot be loaded for testing.', 'Load Recipe');
            return;
        }
        if (!batch) {
            showAppModal('Please enter a batch number.', 'Load Recipe');
            return;
        }
        var recipe = Object.assign({}, pendingRecipeToLoad);
        closeBatchNumberModal();
        _finalizeRecipeLoad(recipe, { batchNumber1: batch, batchNumber: batch });
    };
    // === Sieve Shaker Validation ===
    var _valState = {
        running: false,
        type: 'CONTINUOUS',
        amplitude: 15,
        amplitudeDisplay: 1.5,
        durationSec: 300,
        pollInterval: null,
        startTime: 0,
        startIso: null,
        runEndElapsedSeconds: 0,
        aborted: false,
        awaitingActualAmplitude: false
    };

    function _valCaptureElapsed() {
        return _valState.startTime ? Math.floor((Date.now() - _valState.startTime) / 1000) : 0;
    }

    function _valNowIso() {
        return typeof formatLocalWallClockIso === 'function' ? formatLocalWallClockIso() : new Date().toISOString();
    }

    function _valIsIntermittent(type) {
        var t = String(type || '').toUpperCase();
        return t === 'INTERMITTENT' || t === 'INTERMEDIATE' || t === 'I';
    }

    function _valTypeLabel(type) {
        return _valIsIntermittent(type) ? 'Intermittent' : 'Continuous';
    }

    function _valNormalizeType(type) {
        return _valIsIntermittent(type) ? 'INTERMITTENT' : 'CONTINUOUS';
    }

    function _valWriteCheckpoint(phase) {
        try {
            var elapsed = _valState.runEndElapsedSeconds || _valCaptureElapsed();
            var nowIso = _valNowIso();
            var payload = {
                type: 'validation',
                name: 'Sieve Shaker Validation - ' + (_valTypeLabel(_valState.type)),
                testData: {
                    testType: 'VALIDATION',
                    validationType: _valState.type,
                    shakerMode: _valNormalizeType(_valState.type),
                    setAmplitude: _valState.amplitude,
                    amplitude: _valState.amplitude,
                    durationSeconds: _valState.durationSec,
                    setDurationSeconds: _valState.durationSec,
                    actualElapsedSeconds: elapsed,
                    elapsedSeconds: elapsed,
                    status: _valState.running ? 'running' : (_valState.aborted ? 'Aborted' : 'Completed'),
                    validationStartTime: _valState.startIso || nowIso,
                    validationEndTime: nowIso,
                    testStartTime: _valState.startIso || nowIso,
                    testEndTime: nowIso,
                    testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : ''
                },
                _checkpointPhase: phase || 'running',
                _checkpointAt: nowIso,
                createdAt: _valState.startIso || nowIso,
                completedAt: nowIso
            };
            return apiRequest(API_BASE + '/api/data/test-run/checkpoint', { method: 'PUT', body: payload })
                .catch(function () { return null; });
        } catch (e) {
            return Promise.resolve(null);
        }
    }

    function _valClearCheckpoint() {
        return apiRequest(API_BASE + '/api/data/test-run/checkpoint', { method: 'DELETE' })
            .catch(function () { return null; });
    }

    window._srIsValidationRunning = function () {
        return !!(_valState && _valState.running);
    };

    window._srIsValidationSessionActive = function () {
        return !!(_valState && (_valState.running || _valState.awaitingActualAmplitude));
    };

    window.startShakerValidation = function () {
        if (typeof userCanRunValidation === 'function' && !userCanRunValidation()) {
            if (typeof denyPermission === 'function') denyPermission('run validation');
            return;
        }
        var typeEl = document.querySelector('input[name="validation-type-select"]:checked');
        _valState.type = typeEl ? typeEl.value : 'CONTINUOUS';
        var ampEl = document.getElementById('val-set-amplitude');
        var ampRaw = parseFloat((ampEl || {}).value);
        if (isNaN(ampRaw) || ampRaw < 0.5 || ampRaw > 3.0) {
            showAppModal('Please enter amplitude between 0.5 and 3.0.', 'Validation');
            return;
        }
        var durEl = document.getElementById('val-set-duration');
        var durSec = typeof parseMmSsToSeconds === 'function'
            ? parseMmSsToSeconds((durEl || {}).value)
            : null;
        if (durSec == null || durSec < 1) {
            showAppModal('Please enter a valid set duration (MM:SS).', 'Validation');
            return;
        }
        _valState.amplitude = Math.round(ampRaw * 10);
        _valState.amplitudeDisplay = ampRaw;
        _valState.durationSec = durSec;
        _valState.running = false;
        _valState.aborted = false;
        _valState.awaitingActualAmplitude = false;
        _valState.startTime = null;
        _valState.startIso = null;
        _valState.type = _valNormalizeType(_valState.type);

        var typeLabel = _valTypeLabel(_valState.type);
        var durLabel = typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(durSec) : String(durSec);

        var el;
        el = document.getElementById('val-run-type'); if (el) el.textContent = typeLabel;
        el = document.getElementById('val-run-amplitude');
        if (el) {
            el.textContent = (typeof formatAmplitudeDisplay === 'function')
                ? formatAmplitudeDisplay(_valState.amplitudeDisplay != null ? _valState.amplitudeDisplay : _valState.amplitude)
                : String(_valState.amplitudeDisplay != null ? _valState.amplitudeDisplay : (_valState.amplitude / 10));
        }
        el = document.getElementById('val-run-duration'); if (el) el.textContent = durLabel;
        el = document.getElementById('val-run-status'); if (el) { el.textContent = 'Ready'; el.className = 'val-run-stat-value val-run-status-text is-ready'; el.style.color = ''; }
        el = document.getElementById('val-run-status-sub'); if (el) el.textContent = 'Press Start to run the shaker';
        el = document.getElementById('val-drum-timer'); if (el) el.textContent = '00:00';
        el = document.getElementById('val-confirm-section'); if (el) el.style.display = 'none';
        el = document.getElementById('val-actual-amplitude'); if (el) el.value = '';
        var btn = document.getElementById('btn-validation-start-abort');
        if (btn) { btn.style.display = ''; btn.style.background = ''; btn.disabled = false; }
        el = document.getElementById('btn-validation-label'); if (el) el.textContent = 'Start Validation';
        var ctrlIcon = btn && btn.querySelector('.ctrl-icon');
        if (ctrlIcon) ctrlIcon.innerHTML = '&#9654;';

        goToPage('validation-run');
    };

    window.toggleValidationRunState = function () {
        if (_valState.running) {
            _confirmAbort('validation', function () { _stopShakerValidation(true); });
            return;
        }
        var program = {
            shakerMode: _valNormalizeType(_valState.type),
            amplitude: _valState.amplitude,
            durationSeconds: _valState.durationSec
        };
        apiRequest(API_BASE + '/api/hardware/shaker/start', { method: 'POST', body: program }).then(function () {
            _valState.running = true;
            _valState.aborted = false;
            _valState.startTime = Date.now();
            _valState.startIso = _valNowIso();
            var typeLabel = _valTypeLabel(_valState.type);
            var durLabel = typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(_valState.durationSec) : String(_valState.durationSec);
            if (typeof logAuditEvent === 'function') {
                logAuditEvent('Validation started', typeLabel + ' validation run started | amp ' +
                    (_valState.amplitudeDisplay != null ? _valState.amplitudeDisplay : (_valState.amplitude / 10)) +
                    ' | set duration ' + durLabel, {
                    eventType: 'lifecycle',
                    entityType: 'validation',
                    extra: { validationType: _valState.type }
                });
            }
            var el = document.getElementById('val-run-status'); if (el) { el.textContent = 'Running'; el.className = 'val-run-stat-value val-run-status-text'; el.style.color = '#e67e22'; }
            el = document.getElementById('val-run-status-sub'); if (el) el.textContent = 'Shaker active \u2014 observe externally';
            var btn = document.getElementById('btn-validation-start-abort');
            if (btn) { btn.style.background = '#ef4444'; }
            el = document.getElementById('btn-validation-label'); if (el) el.textContent = 'Abort';
            var ctrlIcon = btn && btn.querySelector('.ctrl-icon');
            if (ctrlIcon) ctrlIcon.innerHTML = '&#9632;';
            _valWriteCheckpoint('running');
            _startValPoll();
        }).catch(function (err) {
            showAppModal('Failed to start shaker: ' + (err.message || err), 'Validation');
        });
    };

    function _stopShakerValidation(aborted) {
        var mode = _valIsIntermittent(_valState.type) ? 'I' : 'C';
        apiRequest(API_BASE + '/api/hardware/shaker/stop', { method: 'POST', body: { mode: mode } }).catch(function () {});
        _valState.runEndElapsedSeconds = _valCaptureElapsed();
        _valState.running = false;
        _valState.aborted = !!aborted;
        _stopValPoll();
        var timerEl = document.getElementById('val-drum-timer');
        if (timerEl && typeof formatSecondsToMmSs === 'function') {
            timerEl.textContent = formatSecondsToMmSs(_valState.runEndElapsedSeconds);
        }
        var el = document.getElementById('val-run-status'); if (el) { el.textContent = aborted ? 'Aborted' : 'Completed'; el.style.color = aborted ? '#ef4444' : '#27ae60'; }
        el = document.getElementById('val-run-status-sub'); if (el) el.textContent = aborted ? 'Test aborted.' : 'Enter the measured amplitude below';
        var btn = document.getElementById('btn-validation-start-abort');
        if (btn) { btn.style.background = ''; btn.disabled = true; }
        if (aborted) {
            _valState.awaitingActualAmplitude = false;
            _saveValidationReportAndPreview(null);
        } else {
            _valState.awaitingActualAmplitude = true;
            if (typeof markAutoLogoutActivity === 'function') {
                try { markAutoLogoutActivity(); } catch (e0) {}
            }
            el = document.getElementById('val-confirm-section');
            if (el) el.style.display = 'grid';
            var ampInp = document.getElementById('val-actual-amplitude');
            if (ampInp) {
                ampInp.classList.add('decimal-input');
                ampInp.setAttribute('inputmode', 'decimal');
                ampInp.setAttribute('data-decimal-input', 'true');
                setTimeout(function () {
                    try { ampInp.focus(); } catch (e1) {}
                    if (typeof openOSKForInput === 'function') {
                        try { openOSKForInput(ampInp); } catch (e2) {}
                    } else if (typeof showOSK === 'function') {
                        try { showOSK(ampInp); } catch (e3) {}
                    }
                }, 80);
            }
        }
    }

    function _startValPoll() {
        if (_valState.pollInterval) clearInterval(_valState.pollInterval);
        _valState.pollInterval = setInterval(function () {
            if (!_valState.running || !_valState.startTime) return;
            var elapsed = Math.floor((Date.now() - _valState.startTime) / 1000);
            var el = document.getElementById('val-drum-timer');
            if (el && typeof formatSecondsToMmSs === 'function') el.textContent = formatSecondsToMmSs(elapsed);
            _valWriteCheckpoint('running');
            if (elapsed >= (_valState.durationSec || 0)) {
                _valState.runEndElapsedSeconds = elapsed;
                _stopShakerValidation(false);
            }
        }, 1000);
    }

    function _stopValPoll() {
        if (_valState.pollInterval) { clearInterval(_valState.pollInterval); _valState.pollInterval = null; }
    }

    function _saveValidationReportAndPreview(actualAmp) {
        _valState.awaitingActualAmplitude = false;
        var confirmEl = document.getElementById('val-confirm-section');
        if (confirmEl) confirmEl.style.display = 'none';
        var elapsed = _valState.runEndElapsedSeconds || _valCaptureElapsed();
        var endIso = _valNowIso();
        var startIso = _valState.startIso || endIso;
        var setDurLabel = typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(_valState.durationSec) : String(_valState.durationSec);
        var testDurLabel = typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(elapsed) : String(elapsed);
        var detail = 'Set Amplitude: ' + (_valState.amplitudeDisplay != null ? _valState.amplitudeDisplay : _valState.amplitude) +
            ' | Actual Amplitude: ' + (actualAmp != null ? actualAmp : 'n/a') +
            ' | Type: ' + (_valTypeLabel(_valState.type)) +
            ' | Set Duration: ' + setDurLabel +
            ' | Test Duration: ' + testDurLabel +
            (_valState.aborted ? ' | Aborted' : '');

        if (typeof logAuditEvent === 'function') {
            logAuditEvent(_valState.aborted ? 'Validation aborted' : 'Validation finished', detail, {
                eventType: 'lifecycle', entityType: 'validation', entityName: _valState.type
            });
        }

        var validationReport = {
            testType: 'VALIDATION',
            validationType: _valState.type,
            shakerMode: _valNormalizeType(_valState.type),
            setAmplitude: _valState.amplitude,
            amplitude: _valState.amplitude,
            actualAmplitude: actualAmp,
            durationSeconds: _valState.durationSec,
            setDurationSeconds: _valState.durationSec,
            actualElapsedSeconds: elapsed,
            elapsedSeconds: elapsed,
            status: _valState.aborted ? 'Aborted' : 'Completed',
            aborted: _valState.aborted || false,
            validationStartTime: startIso,
            validationEndTime: endIso,
            testStartTime: startIso,
            testEndTime: endIso,
            testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : '',
            createdAt: startIso
        };

        apiRequest(API_BASE + '/api/data/reports', {
            method: 'POST',
            body: {
                type: 'validation',
                name: 'Sieve Shaker Validation - ' + _valTypeLabel(_valState.type),
                testData: validationReport,
                isValidation: true,
                createdAt: startIso,
                completedAt: endIso
            }
        }).then(function (res) {
            return _valClearCheckpoint().then(function () { return res; });
        }).then(function (res) {
            var reportId = res && (res.id != null ? res.id : (res.report && res.report.id));
            if (typeof finishTestRunReportSaved === 'function') {
                finishTestRunReportSaved(reportId);
            } else if (reportId != null && typeof openReportPreview === 'function') {
                openReportPreview(reportId, { setGate: true });
            } else {
                goToPage('reports');
            }
        }).catch(function () {
            showAppModal('Failed to save validation report.', 'Validation');
        });
    }

    window.submitValidationResult = function () {
        var raw = ((document.getElementById('val-actual-amplitude') || {}).value || '').trim();
        var actualAmp = raw === '' ? null : parseFloat(raw);
        if (actualAmp == null || isNaN(actualAmp) || actualAmp < 0.5 || actualAmp > 3.0) {
            showAppModal('Please enter actual amplitude between 0.5 and 3.0.', 'Validation');
            return;
        }
        _saveValidationReportAndPreview(actualAmp);
    };

    window._srAbortValidationForLogout = function () {
        if (!_valState.running && !_valState.awaitingActualAmplitude) return Promise.resolve();
        _valState.aborted = true;
        _valState.running = false;
        _valState.awaitingActualAmplitude = false;
        _stopValPoll();
        var mode = _valIsIntermittent(_valState.type) ? 'I' : 'C';
        return apiRequest(API_BASE + '/api/hardware/shaker/stop', { method: 'POST', body: { mode: mode } })
            .catch(function () { return null; })
            .then(function () {
                var elapsed = _valState.startTime ? Math.floor((Date.now() - _valState.startTime) / 1000) : 0;
                var endIso = _valNowIso();
                var startIso = _valState.startIso || endIso;
                var payload = {
                    type: 'validation',
                    testData: {
                        testType: 'VALIDATION',
                        validationType: _valState.type,
                        setAmplitude: _valState.amplitude,
                        amplitude: _valState.amplitude,
                        durationSeconds: _valState.durationSec,
                        setDurationSeconds: _valState.durationSec,
                        actualElapsedSeconds: elapsed,
                        elapsedSeconds: elapsed,
                        status: 'Aborted',
                        aborted: true,
                        validationStartTime: startIso,
                        validationEndTime: endIso,
                        testStartTime: startIso,
                        testEndTime: endIso,
                        testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : ''
                    },
                    createdAt: startIso,
                    completedAt: endIso
                };
                if (typeof logAuditEvent === 'function') {
                    logAuditEvent('Validation aborted', 'Logout abort | Test Duration ' +
                        (typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(elapsed) : elapsed), {
                        eventType: 'lifecycle', entityType: 'validation'
                    });
                }
                return apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: payload })
                    .then(function () { return _valClearCheckpoint(); })
                    .catch(function () { return _valClearCheckpoint(); });
            });
    };

    // ===== ABORT CONFIRM HELPER =====
    function _confirmAbort(context, onConfirm) {
        var msg = context === 'validation'
            ? 'Do you want to abort the validation run?'
            : 'Do you want to abort the test?';
        if (typeof showConfirmModal === 'function') {
            showConfirmModal(msg, 'Abort').then(function (ok) { if (ok) onConfirm(); });
        } else {
            if (confirm(msg)) onConfirm();
        }
    }

    // ===== NAVIGATION GUARDS (called by goToPage in script.js) =====
    // These expose the hooks that goToPage already expects.
    window.isValidationNavigationBlocked = function () {
        return !!(_valState.running || _valState.awaitingActualAmplitude);
    };

    window.confirmAbortValidationForNavigation = function () {
        return new Promise(function (resolve) {
            _confirmAbort('validation', function () {
                _stopShakerValidation(true);
                resolve(true);
            });
            // If user cancels the modal the promise just never resolves — goToPage won't proceed.
            // We need to resolve false on cancel. Use showConfirmModal directly:
        });
    };

    // Override with proper cancel handling
    window.confirmAbortValidationForNavigation = function () {
        return new Promise(function (resolve) {
            var msg = 'Do you want to abort the validation run?';
            if (typeof showConfirmModal === 'function') {
                showConfirmModal(msg, 'Abort').then(function (ok) {
                    if (ok) { _stopShakerValidation(true); resolve(true); }
                    else resolve(false);
                });
            } else {
                if (confirm(msg)) { _stopShakerValidation(true); resolve(true); }
                else resolve(false);
            }
        });
    };

    window._srIsActiveTestOperation = function () {
        if (typeof window._srIsValidationSessionActive === 'function' && window._srIsValidationSessionActive()) return true;
        if (typeof window._srIsValidationRunning === 'function' && window._srIsValidationRunning()) return true;
        if (_sr.weighingActive) return true;
        var bw = document.getElementById('tr-before-wizard');
        var aw = document.getElementById('tr-after-wizard');
        if (bw && bw.style.display && bw.style.display !== 'none') return true;
        if (aw && aw.style.display && aw.style.display !== 'none') return true;
        return !!(_sr.running && !_sr.done);
    };

    // Hooks expected by goToPage in script.js
    window._trIsActiveTestOperation = function () {
        return window._srIsActiveTestOperation();
    };

    window._trAbortRunningTestNow = function () {
        stopScalePoll('wz');
        _wzOnWeight = null;
        if (!(_sr.running || _sr.weighingActive || _sr.done)) return Promise.resolve();
        _sr.abortedRun = true;
        var save = function () {
            _sr.running = false;
            _sr.done = true;
            _srStopPoll();
            _srSetAnimating(false);
            _wzHideAndClear('tr-before-wizard');
            _wzHideAndClear('tr-after-wizard');
            _sr.weighingActive = false;
            return _srSavePartialReport();
        };
        if (_sr.running) {
            return apiRequest(API_BASE + '/api/hardware/shaker/abort', { method: 'POST', body: {} })
                .catch(function () { return null; })
                .then(function () { return save(); });
        }
        return save();
    };

    window._trConfirmAbortRunningTest = function () {
        return new Promise(function (resolve) {
            var msg = 'Do you want to abort the test?';
            if (typeof showConfirmModal === 'function') {
                showConfirmModal(msg, 'Abort').then(function (ok) {
                    if (ok) {
                        logAuditEvent('Test aborted', 'Navigation abort', { eventType: 'lifecycle', outcome: 'aborted' });
                        apiRequest(API_BASE + '/api/hardware/shaker/abort', { method: 'POST', body: {} })
                            .then(function () { _srFinishRun(true); resolve(true); })
                            .catch(function () { _srFinishRun(true); resolve(true); });
                    } else {
                        resolve(false);
                    }
                });
            } else {
                if (confirm(msg)) { _srFinishRun(true); resolve(true); }
                else resolve(false);
            }
        });
    };

})();
