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
        var isIntermittent = mode === 'INTERMITTENT';
        var isLogical = mode === 'LOGICAL';
        if (durationWrap) durationWrap.style.display = isLogical ? 'none' : '';
        if (onWrap) onWrap.style.display = isIntermittent ? '' : 'none';
        if (offWrap) offWrap.style.display = isIntermittent ? '' : 'none';
        if (logicalWrap) logicalWrap.style.display = isLogical ? '' : 'none';
        if (isLogical) updateLogicalCycles('quick');
    };

    window.applyRecipeShakerModeToFields = function () {
        var mode = getRecipeShakerMode();
        var durationWrap = document.getElementById('recipe-duration-wrap');
        var onWrap = document.getElementById('recipe-on-time-wrap');
        var offWrap = document.getElementById('recipe-off-time-wrap');
        var logicalWrap = document.getElementById('recipe-logical-segments-wrap');
        var isIntermittent = mode === 'INTERMITTENT';
        var isLogical = mode === 'LOGICAL';
        if (durationWrap) durationWrap.style.display = isLogical ? 'none' : '';
        if (onWrap) onWrap.style.display = isIntermittent ? '' : 'none';
        if (offWrap) offWrap.style.display = isIntermittent ? '' : 'none';
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
                    if (data && data.ok && data.weight != null && parseFloat(data.weight) > 0) {
                        if (_wzOnWeight) _wzOnWeight(parseFloat(data.weight));
                    }
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

    window.renderSieveSizeFields = function (prefix) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        var wrapEl = document.getElementById(prefix + '-sieve-sizes-wrap');
        if (!numEl || !wrapEl) return;
        var n = Math.max(1, Math.min(8, parseInt(numEl.value, 10) || 5));
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
    };

    window.openMicronPicker = function (prefix, sieveIdx) {
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
        var btn = document.getElementById(prefix + '-sieve-size-' + idx);
        var hidden = document.getElementById(prefix + '-sieve-val-' + idx);
        if (btn) {
            btn.innerHTML = '<span class="mb-mesh">' + mesh + '</span>' +
                '<span class="mb-micron">' + micron + ' \u00b5m</span>';
            btn.dataset.value = String(micron);
            btn.classList.add('selected');
        }
        if (hidden) hidden.value = String(micron);
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

    function collectSieveData(prefix) {
        var numEl = document.getElementById(prefix + '-num-sieves');
        var n = Math.max(1, Math.min(8, parseInt((numEl || {}).value, 10) || 5));
        var sizes = [];
        for (var i = 1; i <= n; i++) {
            var hidden = document.getElementById(prefix + '-sieve-val-' + i);
            var btn = document.getElementById(prefix + '-sieve-size-' + i);
            var v = hidden ? parseInt(hidden.value, 10) : (btn ? parseInt(btn.dataset.value, 10) : 0);
            sizes.push(isNaN(v) ? 0 : v);
        }
        return { numSieves: n, sieveSizes: sizes };
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
            if (mode === 'INTERMITTENT') {
                var onSec = parseMmSsToSeconds((document.getElementById('quick-on-time') || {}).value);
                var offSec = parseMmSsToSeconds((document.getElementById('quick-off-time') || {}).value);
                if (onSec == null || onSec < 1 || offSec == null || offSec < 1) {
                    showAppModal('Please enter valid on/off times (MM:SS).', 'Quick Test');
                    return null;
                }
                recipe.intermittentOnSeconds = onSec;
                recipe.intermittentOffSeconds = offSec;
            }
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
            if (mode === 'INTERMITTENT') {
                var onSec = parseMmSsToSeconds((document.getElementById('recipe-on-time') || {}).value);
                var offSec = parseMmSsToSeconds((document.getElementById('recipe-off-time') || {}).value);
                if (onSec == null || onSec < 1 || offSec == null || offSec < 1) {
                    showAppModal('Please enter valid on/off times (MM:SS).', 'Create Recipe');
                    return;
                }
                recipe.intermittentOnSeconds = onSec;
                recipe.intermittentOffSeconds = offSec;
            }
        }
        var editId = window.currentEditingRecipeId;
        if (editId) recipe.id = editId;
        var url = editId ? (API_BASE + '/api/data/recipes/' + editId) : (API_BASE + '/api/data/recipes');
        var method = editId ? 'PUT' : 'POST';
        apiRequest(url, { method: method, body: recipe }).then(function (result) {
            window.currentEditingRecipeId = null;
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
        livePollInterval: null,
        targetSeconds: 0,
        elapsedSeconds: 0,
        pollStartTime: 0
    };

    function _srEl(id) { return document.getElementById(id); }

    function _srTargetSeconds(recipe) {
        if (!recipe) return 0;
        if (String(recipe.shakerMode || '').toUpperCase() === 'LOGICAL') {
            return computeLogicalTotalSeconds(recipe.logicalSegments || []);
        }
        return parseInt(recipe.durationSeconds, 10) || 0;
    }

    window.initTestRunPage = function (recipe) {
        _sr.recipe = recipe || {};
        _sr.running = false;
        _sr.done = false;
        _sr.abortedRun = false;
        _sr.completedEarly = false;
        _sr.targetSeconds = _srTargetSeconds(_sr.recipe);
        _sr.elapsedSeconds = 0;
        if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }

        if (_srEl('tr-product-name')) _srEl('tr-product-name').textContent = recipe.productName || recipe.name || '--';
        if (_srEl('tr-batch-number')) _srEl('tr-batch-number').textContent = recipe.batchNumber || '--';
        if (_srEl('tr-mode')) _srEl('tr-mode').textContent = shakerModeLabel(recipe.shakerMode);
        if (_srEl('tr-amplitude')) _srEl('tr-amplitude').textContent = recipe.amplitude != null ? (recipe.amplitude / 10).toFixed(1) : '--';
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
        // Hide wizards
        var bw = document.getElementById('tr-before-wizard');
        if (bw) bw.style.display = 'none';
        var aw = document.getElementById('tr-after-wizard');
        if (aw) aw.style.display = 'none';
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
        _sr.running = false;
        _sr.done = true;
        _sr.abortedRun = !!aborted;
        _srStopPoll();
        _srSetAnimating(false);
        _srSetButtons('done');
        if (_srEl('tr-footer-note')) {
            _srEl('tr-footer-note').textContent = aborted ? 'Test aborted.' : 'Test complete.';
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

    // ===== WIZARD RENDER HELPER =====
    function _wzRenderStep(containerId, stepIdx, totalSteps, label, instruction) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var dots = '';
        for (var i = 0; i < totalSteps; i++) {
            var cls = i < stepIdx ? 'wz-dot done' : (i === stepIdx ? 'wz-dot active' : 'wz-dot');
            dots += '<span class="' + cls + '"></span>';
        }
        var isAfterWiz = containerId === 'tr-after-wizard';
        el.innerHTML =
            '<div class="wz-step-indicator">Step ' + (stepIdx + 1) + ' of ' + totalSteps + '</div>' +
            '<div class="wz-dots">' + dots + '</div>' +
            '<div class="wz-label">' + label + '</div>' +
            '<div class="wz-instruction">' + instruction + '</div>' +
            '<div class="wz-weight-display" id="wz-weight-val">Waiting\u2026</div>' +
            '<div class="wz-manual-row" id="wz-manual-row" style="display:none;">' +
            '<input type="number" id="wz-manual-input" class="wz-manual-input" step="0.0001" placeholder="Type weight (g) e.g. 45.9876">' +
            '<button class="wz-btn wz-btn-next" id="wz-manual-confirm" style="padding:10px 20px;">OK</button></div>' +
            '<div class="wz-buttons">' +
            (stepIdx > 0 ? '<button class="wz-btn wz-btn-back" id="wz-back-btn">Back</button>' : '') +
            '<button class="wz-btn" style="background:#64748b;color:#fff;" id="wz-type-btn">Type Manually</button>' +
            '<button class="wz-btn wz-btn-next" id="wz-next-btn" disabled>Next</button>' +
            '</div>' +
            (isAfterWiz ? '<div style="text-align:center;margin-top:10px;"><button class="wz-btn" style="background:#475569;color:#cbd5e1;font-size:13px;padding:8px 18px;" id="wz-skip-btn">Skip &amp; Save Report</button></div>' : '');
    }

    // ===== BEFORE-TEST WIZARD =====
    function _startBeforeWizard(recipe, onComplete) {
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var sieveSizes = recipe.sieveSizes || [];
        var steps = [];
        for (var i = 0; i < numSieves; i++) {
            steps.push({ label: 'Sieve ' + (i + 1) + ' (' + (sieveSizes[i] || '?') + ' \u00b5m)', instruction: 'Place empty sieve on scale \u2014 press PRINT on scale' });
        }
        steps.unshift({ label: 'PAN (Receiver)', instruction: 'Place empty collecting PAN on scale \u2014 press PRINT on scale' });
        steps.push({ label: 'Sample', instruction: 'Place sample on scale \u2014 press PRINT on scale' });

        var weights = [];
        var currentStep = 0;
        var container = document.getElementById('tr-before-wizard');
        var runScreen = document.getElementById('tr-run-screen');
        if (runScreen) runScreen.style.display = 'none';
        if (container) container.style.display = 'flex';

        function renderCurrent() {
            var isManual = getWeighMethod() === 'manual';
            var instr = isManual ? 'Type the weight manually below' : (steps[currentStep].instruction);
            _wzRenderStep('tr-before-wizard', currentStep, steps.length, steps[currentStep].label, instr);
            var nextBtn = document.getElementById('wz-next-btn');
            var backBtn = document.getElementById('wz-back-btn');
            var typeBtn = document.getElementById('wz-type-btn');
            if (nextBtn) nextBtn.onclick = goNext;
            if (backBtn) backBtn.onclick = goBack;
            if (typeBtn) { if (isManual) typeBtn.style.display = 'none'; else typeBtn.onclick = showManualInput; }
            if (isManual) {
                showManualInput();
            } else {
                _wzOnWeight = function (w) {
                    var display = document.getElementById('wz-weight-val');
                    if (display) { display.textContent = w.toFixed(4) + ' g'; display.classList.add('captured'); }
                    weights[currentStep] = w;
                    var nb = document.getElementById('wz-next-btn');
                    if (nb) nb.disabled = false;
                    stopScalePoll('wz');
                };
                startScalePoll('wz');
            }
        }

        function showManualInput() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            var row = document.getElementById('wz-manual-row');
            if (row) row.style.display = 'flex';
            var display = document.getElementById('wz-weight-val');
            if (display) display.textContent = 'Manual Entry';
            var inp = document.getElementById('wz-manual-input');
            // Attach OSK handler to the newly visible input and focus it
            if (inp) {
                if (typeof attachInputFocusHandlers === 'function') attachInputFocusHandlers(row);
                setTimeout(function () { inp.focus(); }, 80);
            }
            var confirmBtn = document.getElementById('wz-manual-confirm');
            if (confirmBtn) confirmBtn.onclick = function () {
                var v = inp ? parseFloat(inp.value) : 0;
                if (!v || v <= 0) return;
                weights[currentStep] = v;
                if (display) { display.textContent = v.toFixed(4) + ' g'; display.classList.add('captured'); }
                var nb = document.getElementById('wz-next-btn');
                if (nb) nb.disabled = false;
                if (row) row.style.display = 'none';
            };
        }

        function goNext() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            currentStep++;
            if (currentStep >= steps.length) {
                if (container) container.style.display = 'none';
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
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var sieveSizes = recipe.sieveSizes || [];
        // Reverse order: sieve N, N-1, ..., 1, PAN
        var steps = [];
        for (var i = numSieves - 1; i >= 0; i--) {
            steps.push({ label: 'Sieve ' + (i + 1) + ' (' + (sieveSizes[i] || '?') + ' \u00b5m)', idx: i });
        }
        steps.push({ label: 'PAN (Receiver)', idx: -1 });

        var afterWeights = []; // in collection order (N..1, PAN)
        var currentStep = 0;
        var container = document.getElementById('tr-after-wizard');
        var runScreen = document.getElementById('tr-run-screen');
        if (runScreen) runScreen.style.display = 'none';
        if (container) container.style.display = 'flex';

        function renderCurrent() {
            var isManual = getWeighMethod() === 'manual';
            var instr = isManual ? 'Type the weight manually below' : 'Place sieve with powder on scale \u2014 press PRINT on scale';
            _wzRenderStep('tr-after-wizard', currentStep, steps.length + 1, steps[currentStep].label, instr);
            var nextBtn = document.getElementById('wz-next-btn');
            var backBtn = document.getElementById('wz-back-btn');
            var typeBtn = document.getElementById('wz-type-btn');
            if (nextBtn) nextBtn.onclick = goNext;
            if (backBtn) backBtn.onclick = goBack;
            if (typeBtn) { if (isManual) typeBtn.style.display = 'none'; else typeBtn.onclick = showManualInput; }
            var skipBtn = document.getElementById('wz-skip-btn');
            if (skipBtn) skipBtn.onclick = skipAndSaveReport;
            if (isManual) {
                showManualInput();
            } else {
                _wzOnWeight = function (w) {
                    var display = document.getElementById('wz-weight-val');
                    if (display) { display.textContent = w.toFixed(4) + ' g'; display.classList.add('captured'); }
                    afterWeights[currentStep] = w;
                    var nb = document.getElementById('wz-next-btn');
                    if (nb) nb.disabled = false;
                    stopScalePoll('wz');
                };
                startScalePoll('wz');
            }
        }

        function skipAndSaveReport() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            if (container) container.style.display = 'none';
            // Save report with partial/no after-weights
            _sr.afterWeightsByIdx = [];
            _sr.fractions = [];
            _sr.panFraction = 0;
            _sr.totalFraction = 0;
            if (typeof submitSieveWeights === 'function') submitSieveWeights();
        }

        function showManualInput() {
            stopScalePoll('wz');
            _wzOnWeight = null;
            var row = document.getElementById('wz-manual-row');
            if (row) row.style.display = 'flex';
            var display = document.getElementById('wz-weight-val');
            if (display) display.textContent = 'Manual Entry';
            var inp = document.getElementById('wz-manual-input');
            // Attach OSK handler to the newly visible input and focus it
            if (inp) {
                if (typeof attachInputFocusHandlers === 'function') attachInputFocusHandlers(row);
                setTimeout(function () { inp.focus(); }, 80);
            }
            var confirmBtn = document.getElementById('wz-manual-confirm');
            if (confirmBtn) confirmBtn.onclick = function () {
                var v = inp ? parseFloat(inp.value) : 0;
                if (!v || v <= 0) return;
                afterWeights[currentStep] = v;
                if (display) { display.textContent = v.toFixed(4) + ' g'; display.classList.add('captured'); }
                var nb = document.getElementById('wz-next-btn');
                if (nb) nb.disabled = false;
                if (row) row.style.display = 'none';
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
            // Rearrange afterWeights to index order (sieve 0..N-1, PAN)
            var afterByIdx = [];
            for (var j = 0; j < steps.length; j++) {
                var s = steps[j];
                if (s.idx === -1) { afterByIdx[numSieves] = afterWeights[j]; }
                else { afterByIdx[s.idx] = afterWeights[j]; }
            }
            var beforeWeights = _sr.beforeWeights || [];
            // Compute fractions
            var rows = '';
            var totalFraction = 0;
            for (var i = 0; i < numSieves; i++) {
                var bw = beforeWeights[i] || 0;
                var aw = afterByIdx[i] || 0;
                var frac = aw - bw;
                totalFraction += frac;
                rows += '<tr><td>' + (i + 1) + '</td><td>' + (sieveSizes[i] || '--') + '</td><td>' + bw.toFixed(4) + '</td><td>' + aw.toFixed(4) + '</td><td>' + frac.toFixed(4) + '</td></tr>';
            }
            // PAN
            var panBefore = beforeWeights[numSieves] || 0;
            var panAfter = afterByIdx[numSieves] || 0;
            var panFrac = panAfter - panBefore;
            totalFraction += panFrac;
            rows += '<tr><td>PAN</td><td>Receiver</td><td>' + panBefore.toFixed(4) + '</td><td>' + panAfter.toFixed(4) + '</td><td>' + panFrac.toFixed(4) + '</td></tr>';
            rows += '<tr class="wz-summary-total"><td colspan="4">Total Fraction</td><td>' + totalFraction.toFixed(4) + '</td></tr>';

            container.innerHTML =
                '<div class="wz-summary">' +
                '<div class="wz-summary-title">Weight Summary</div>' +
                '<table class="wz-summary-table"><thead><tr><th>Sieve</th><th>\u00b5m</th><th>Before (g)</th><th>After (g)</th><th>Fraction (g)</th></tr></thead><tbody>' + rows + '</tbody></table>' +
                '<div style="font-size:13px;color:#94a3b8;">Sample Weight: ' + (_sr.sampleWeight || 0).toFixed(4) + ' g</div>' +
                '<div class="wz-verdict-row">' +
                '<button class="wz-btn wz-btn-start" style="width:100%;font-size:1.1rem;" onclick="submitSieveWeights()">Save &amp; View Report</button>' +
                '</div></div>';

            // Store computed data
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
        var recipe = _sr.recipe || {};
        var numSieves = parseInt(recipe.numSieves, 10) || 0;
        var isPass = null; // Pass/fail determined on report preview page
        var beforeWeights = _sr.beforeWeights || [];
        var afterWeights = _sr.afterWeightsByIdx || [];
        var sieveWeights = _sr.fractions || [];
        var panFraction = _sr.panFraction || 0;
        var sampleWeight = _sr.sampleWeight || 0;

        var payload = {
            name: 'Sieve Shaker Test - ' + (recipe.productName || 'Recipe') + (_sr.abortedRun ? ' (Aborted)' : ''),
            type: 'test',
            recipe: recipe,
            testData: {
                shakerMode: recipe.shakerMode,
                amplitude: recipe.amplitude,
                durationSeconds: _sr.targetSeconds,
                intermittentOnSeconds: recipe.intermittentOnSeconds,
                intermittentOffSeconds: recipe.intermittentOffSeconds,
                logicalSegments: recipe.logicalSegments,
                actualElapsedSeconds: _sr.elapsedSeconds,
                completedEarly: _sr.completedEarly,
                status: _sr.abortedRun ? 'Aborted' : 'Completed',
                testStatus: 'Pending',
                verdict: 'PENDING',
                result: 'PENDING',
                batchNumber: recipe.batchNumber,
                productName: recipe.productName,
                numSieves: numSieves,
                sieveSizes: recipe.sieveSizes || [],
                beforeWeights: beforeWeights,
                afterWeights: afterWeights,
                sieveWeights: sieveWeights,
                panWeight: panFraction,
                initialWeight: sampleWeight,
                finalWeight: _sr.totalFraction || 0,
                weighMethod: getWeighMethod(),
                testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : ''
            }
        };
        apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: payload }).then(function (res) {
            var reportId = res && (res.id != null ? res.id : (res.report && res.report.id));
            if (typeof logAuditEvent === 'function') {
                logAuditEvent('Test finished', 'Sieve shaker test saved | report id ' + (reportId != null ? reportId : '--') + (_sr.abortedRun ? ' (Aborted)' : ''), {
                    eventType: 'lifecycle', entityType: 'report', entityId: reportId != null ? String(reportId) : ''
                });
            }
            var afterWiz = document.getElementById('tr-after-wizard');
            if (afterWiz) afterWiz.style.display = 'none';
            if (typeof finishTestRunReportSaved === 'function') {
                finishTestRunReportSaved(reportId);
            } else if (reportId != null && typeof openReportPreview === 'function') {
                openReportPreview(reportId, { setGate: true });
            } else {
                goToPage('reports');
            }
        }).catch(function () {
            showAppModal('Failed to save report.', 'Test Run');
        });
    };

    window.trHandleStartButton = function () {
        if (_sr.running || _sr.done) return;
        var recipe = _sr.recipe || {};
        // Start before-test weight wizard
        _startBeforeWizard(recipe, function (weights) {
            // weights: [PAN, sieve1..N, sample]
            var numSieves = parseInt(recipe.numSieves, 10) || 0;
            _sr.beforeWeights = []; // index 0..N-1 = sieves, index N = PAN
            for (var wi = 0; wi < numSieves; wi++) { _sr.beforeWeights.push(weights[wi + 1] || 0); }
            _sr.beforeWeights.push(weights[0] || 0); // PAN at end
            _sr.sampleWeight = weights[numSieves + 1] || 0;
            // Now start the actual hardware program
            var runScreen = document.getElementById('tr-run-screen');
            if (runScreen) runScreen.style.display = '';
            // Start timer immediately so elapsed time runs regardless of API latency
            _sr.running = true;
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
                        showAppModal((res && res.error) ? String(res.error) : 'Failed to start shaker program.', 'Test Run');
                        return;
                    }
                    _srAuditStarted(recipe);
                })
                .catch(function (err) {
                    _sr.running = false;
                    if (_sr.livePollInterval) { clearInterval(_sr.livePollInterval); _sr.livePollInterval = null; }
                    _srSetButtons('idle');
                    if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Press Start to begin the shaker program.';
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
    var _valState = { running: false, type: 'CONTINUOUS', amplitude: 15, durationSec: 300, pollInterval: null, startTime: 0 };

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
        _valState.amplitude = Math.round(ampRaw * 10); // backend units (5-30)
        _valState.amplitudeDisplay = ampRaw; // keep original for display
        _valState.durationSec = 300;
        _valState.running = false;
        _valState.aborted = false;
        _valState.startTime = null;

        var typeLabel = _valState.type === 'INTERMEDIATE' ? 'Intermediate' : 'Continuous';

        var el;
        el = document.getElementById('val-run-type'); if (el) el.textContent = typeLabel;
        el = document.getElementById('val-run-amplitude'); if (el) el.textContent = String(_valState.amplitudeDisplay != null ? _valState.amplitudeDisplay : (_valState.amplitude / 10));
        el = document.getElementById('val-run-status'); if (el) { el.textContent = 'Ready'; el.className = 'val-run-stat-value val-run-status-text is-ready'; el.style.color = ''; }
        el = document.getElementById('val-run-status-sub'); if (el) el.textContent = 'Press Start to run the shaker';
        el = document.getElementById('val-drum-timer'); if (el) el.textContent = '00:00';
        el = document.getElementById('val-confirm-section'); if (el) el.style.display = 'none';
        el = document.getElementById('val-actual-amplitude'); if (el) el.value = '';
        var btn = document.getElementById('btn-validation-start-abort');
        if (btn) { btn.style.display = ''; btn.style.background = ''; }
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
        // Start the shaker
        var program = {
            shakerMode: _valState.type === 'INTERMEDIATE' ? 'INTERMITTENT' : 'CONTINUOUS',
            amplitude: _valState.amplitude,
            durationSeconds: _valState.durationSec
        };
        apiRequest(API_BASE + '/api/hardware/shaker/start', { method: 'POST', body: program }).then(function () {
            _valState.running = true;
            _valState.startTime = Date.now();
            var el = document.getElementById('val-run-status'); if (el) { el.textContent = 'Running'; el.className = 'val-run-stat-value val-run-status-text'; el.style.color = '#e67e22'; }
            el = document.getElementById('val-run-status-sub'); if (el) el.textContent = 'Shaker active \u2014 observe externally';
            // Turn button red / Abort
            var btn = document.getElementById('btn-validation-start-abort');
            if (btn) { btn.style.background = '#ef4444'; }
            el = document.getElementById('btn-validation-label'); if (el) el.textContent = 'Abort';
            var ctrlIcon = btn && btn.querySelector('.ctrl-icon');
            if (ctrlIcon) ctrlIcon.innerHTML = '&#9632;';
            _startValPoll();
        }).catch(function (err) {
            showAppModal('Failed to start shaker: ' + (err.message || err), 'Validation');
        });
    };

    function _stopShakerValidation(aborted) {
        apiRequest(API_BASE + '/api/hardware/shaker/stop', { method: 'POST', body: {} }).catch(function () {});
        _valState.running = false;
        _valState.aborted = !!aborted;
        _stopValPoll();
        var el = document.getElementById('val-run-status'); if (el) { el.textContent = aborted ? 'Aborted' : 'Completed'; el.style.color = aborted ? '#ef4444' : '#27ae60'; }
        el = document.getElementById('val-run-status-sub'); if (el) el.textContent = aborted ? 'Test aborted.' : 'Enter the measured amplitude below';
        var btn = document.getElementById('btn-validation-start-abort');
        if (btn) { btn.style.background = ''; btn.disabled = true; }
        if (aborted) {
            // Skip amplitude — save report and go to preview directly
            _saveValidationReportAndPreview(null);
        } else {
            el = document.getElementById('val-confirm-section'); if (el) el.style.display = '';
        }
    }

    function _startValPoll() {
        if (_valState.pollInterval) clearInterval(_valState.pollInterval);
        _valState.pollInterval = setInterval(function () {
            var elapsed = Math.floor((Date.now() - _valState.startTime) / 1000);
            var el = document.getElementById('val-drum-timer');
            if (el && typeof formatSecondsToMmSs === 'function') el.textContent = formatSecondsToMmSs(elapsed);
        }, 1000);
    }

    function _stopValPoll() {
        if (_valState.pollInterval) { clearInterval(_valState.pollInterval); _valState.pollInterval = null; }
    }

    function _saveValidationReportAndPreview(actualAmp) {
        var elapsed = _valState.startTime ? Math.floor((Date.now() - _valState.startTime) / 1000) : 0;
        var detail = 'Set Amplitude: ' + _valState.amplitude +
            ' | Actual Amplitude: ' + (actualAmp != null ? actualAmp : 'n/a') +
            ' | Type: ' + (_valState.type === 'INTERMEDIATE' ? 'Intermediate' : 'Continuous') +
            ' | Duration: ' + (typeof formatSecondsToMmSs === 'function' ? formatSecondsToMmSs(elapsed) : '--') +
            (_valState.aborted ? ' | Aborted' : '');

        if (typeof logAuditEvent === 'function') {
            logAuditEvent('Validation ' + (_valState.aborted ? 'aborted' : 'completed'), detail, {
                eventType: 'validation', entityType: 'validation', entityName: _valState.type
            });
        }

        var validationReport = {
            testType: 'VALIDATION',
            validationType: _valState.type,
            setAmplitude: _valState.amplitude,
            actualAmplitude: actualAmp,
            elapsedSeconds: elapsed,
            aborted: _valState.aborted || false,
            testedBy: typeof getCurrentUser === 'function' ? getCurrentUser() : '',
            createdAt: typeof formatLocalWallClockIso === 'function' ? formatLocalWallClockIso() : new Date().toISOString()
        };

        apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: { type: 'validation', testData: validationReport, isValidation: true } }).then(function (res) {
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
        var actualAmp = parseFloat((document.getElementById('val-actual-amplitude') || {}).value) || null;
        _saveValidationReportAndPreview(actualAmp);
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
        return !!(_valState.running);
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
        return !!(_sr.running && !_sr.done);
    };

    // Hooks expected by goToPage in script.js
    window._trIsActiveTestOperation = function () {
        return window._srIsActiveTestOperation();
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
