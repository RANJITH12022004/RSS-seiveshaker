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
        if (isLogical && window._quickLogicalSegments.length < 1) {
            window._quickLogicalSegments = [
                { type: 'run', duration: '05:00', durationSeconds: 300 },
                { type: 'wait', duration: '05:00', durationSeconds: 300 }
            ];
            renderLogicalSegments('quick-logical-segments-list', window._quickLogicalSegments, 'quick-logical-total-time', 'quick');
        }
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
        if (isLogical && window._recipeLogicalSegments.length < 1) {
            window._recipeLogicalSegments = [
                { type: 'run', duration: '05:00', durationSeconds: 300 },
                { type: 'wait', duration: '05:00', durationSeconds: 300 }
            ];
            renderLogicalSegments('recipe-logical-segments-list', window._recipeLogicalSegments, 'recipe-logical-total-time', 'recipe');
        }
    };

    function buildShakerRecipeFromQuickForm() {
        var productName = (document.getElementById('quick-product-name') || {}).value || '';
        var batchNumber = (document.getElementById('quick-batch-number') || {}).value || '';
        var amplitude = parseInt((document.getElementById('quick-amplitude') || {}).value, 10);
        var mode = getQuickShakerMode();
        productName = productName.trim();
        batchNumber = batchNumber.trim();
        if (!productName || !batchNumber) {
            showAppModal('Please enter recipe name and batch number.', 'Quick Test');
            return null;
        }
        if (isNaN(amplitude) || amplitude < 5 || amplitude > 30) {
            showAppModal('Please enter amplitude between 5 and 30.', 'Quick Test');
            return null;
        }
        var recipe = {
            productName: productName,
            batchNumber: batchNumber,
            shakerMode: mode,
            amplitude: amplitude,
            quickTest: true
        };
        if (mode === 'LOGICAL') {
            syncLogicalSegmentsFromDom('quick');
            var segments = window._quickLogicalSegments.slice();
            if (!segments.length) {
                showAppModal('Add at least one logical segment.', 'Quick Test');
                return null;
            }
            recipe.logicalSegments = segments.map(function (s) {
                var sec = parseMmSsToSeconds(s.duration) || parseInt(s.durationSeconds, 10);
                return { type: s.type, durationSeconds: sec };
            });
            recipe.durationSeconds = computeLogicalTotalSeconds(recipe.logicalSegments);
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
        var amplitude = parseInt((document.getElementById('recipe-amplitude') || {}).value, 10);
        var mode = getRecipeShakerMode();
        if (!productName) {
            showAppModal('Please enter recipe name.', 'Create Recipe');
            return;
        }
        if (isNaN(amplitude) || amplitude < 5 || amplitude > 30) {
            showAppModal('Please enter amplitude between 5 and 30.', 'Create Recipe');
            return;
        }
        var recipe = {
            productName: productName,
            shakerMode: mode,
            amplitude: amplitude,
            createdAt: (typeof formatLocalWallClockIso === 'function') ? formatLocalWallClockIso() : new Date().toISOString()
        };
        if (mode === 'LOGICAL') {
            syncLogicalSegmentsFromDom('recipe');
            var segments = window._recipeLogicalSegments.slice();
            if (!segments.length) {
                showAppModal('Add at least one logical segment.', 'Create Recipe');
                return;
            }
            recipe.logicalSegments = segments.map(function (s) {
                var sec = parseMmSsToSeconds(s.duration) || parseInt(s.durationSeconds, 10);
                return { type: s.type, durationSeconds: sec };
            });
            recipe.durationSeconds = computeLogicalTotalSeconds(recipe.logicalSegments);
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
        elapsedSeconds: 0
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
        if (_srEl('tr-amplitude')) _srEl('tr-amplitude').textContent = String(recipe.amplitude != null ? recipe.amplitude : '--');
        if (_srEl('tr-target-duration')) _srEl('tr-target-duration').textContent = formatSecondsToMmSs(_sr.targetSeconds);
        if (_srEl('tr-phase')) _srEl('tr-phase').textContent = 'Off';
        if (_srEl('tr-timer')) _srEl('tr-timer').textContent = '00:00';
        if (_srEl('tr-remaining')) _srEl('tr-remaining').textContent = 'Remaining: ' + formatSecondsToMmSs(_sr.targetSeconds);
        if (_srEl('tr-segment-info')) _srEl('tr-segment-info').textContent = '';
        if (_srEl('tr-progress-fill')) _srEl('tr-progress-fill').style.width = '0%';
        if (_srEl('tr-progress-text')) _srEl('tr-progress-text').textContent = '0%';
        if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Press Start to begin the shaker program.';
        _srSetButtons('idle');
    };

    function _srSetButtons(state) {
        var start = _srEl('tr-start-btn');
        var complete = _srEl('tr-complete-btn');
        var stop = _srEl('tr-stop-btn');
        if (!start || !stop) return;
        if (state === 'idle') {
            start.style.display = '';
            start.disabled = false;
            start.textContent = 'Start';
            if (complete) complete.style.display = 'none';
            stop.disabled = false;
        } else if (state === 'running') {
            start.style.display = 'none';
            if (complete) { complete.style.display = ''; complete.disabled = false; }
            stop.disabled = false;
        } else if (state === 'done') {
            start.style.display = 'none';
            if (complete) complete.style.display = 'none';
            stop.disabled = true;
        }
    }

    function _srRefreshFromLive(data) {
        if (!data) return;
        var elapsed = parseFloat(data.elapsedSec);
        if (isNaN(elapsed)) elapsed = 0;
        _sr.elapsedSeconds = elapsed;
        var target = parseInt(data.targetDurationSec, 10) || _sr.targetSeconds || 1;
        var remaining = Math.max(0, target - elapsed);
        if (_srEl('tr-timer')) _srEl('tr-timer').textContent = formatSecondsToMmSs(Math.floor(elapsed));
        if (_srEl('tr-remaining')) _srEl('tr-remaining').textContent = 'Remaining: ' + formatSecondsToMmSs(Math.floor(remaining));
        var phase = String(data.phase || 'off');
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
        _sr.livePollInterval = setInterval(_srPollLive, 1000);
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

    function _srFinishRun(aborted) {
        _sr.running = false;
        _sr.done = true;
        _sr.abortedRun = !!aborted;
        _srStopPoll();
        _srSetButtons('done');
        if (_srEl('tr-footer-note')) {
            _srEl('tr-footer-note').textContent = aborted ? 'Test aborted.' : 'Test complete.';
        }
        var recipe = _sr.recipe || {};
        var payload = {
            name: 'Sieve Shaker Test - ' + (recipe.productName || 'Recipe') + (aborted ? ' (Aborted)' : ''),
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
                status: aborted ? 'Aborted' : 'Completed',
                batchNumber: recipe.batchNumber,
                productName: recipe.productName
            }
        };
        apiRequest(API_BASE + '/api/data/reports', { method: 'POST', body: payload }).then(function (res) {
            var reportId = res && (res.id != null ? res.id : (res.report && res.report.id));
            if (typeof openTestRunCompletionApprovalModal === 'function') {
                openTestRunCompletionApprovalModal(reportId, payload);
            } else if (reportId != null && typeof openReportPreview === 'function') {
                openReportPreview(reportId);
            }
        }).catch(function () {
            showAppModal('Test finished but report could not be saved.', 'Test Run');
        });
    }

    window.trHandleStartButton = function () {
        if (_sr.running || _sr.done) return;
        var recipe = _sr.recipe || {};
        apiRequest(API_BASE + '/api/hardware/shaker/run-program', { method: 'POST', body: recipe })
            .then(function (res) {
                if (!res || !res.ok) {
                    showAppModal((res && res.error) ? String(res.error) : 'Failed to start shaker program.', 'Test Run');
                    return;
                }
                _sr.running = true;
                _srSetButtons('running');
                if (_srEl('tr-footer-note')) _srEl('tr-footer-note').textContent = 'Shaker program running…';
                _srAuditStarted(recipe);
                _srStartPoll();
            })
            .catch(function (err) {
                showAppModal('Failed to start: ' + (err && err.message ? err.message : 'Error'), 'Test Run');
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
            if (ampEl && r.amplitude != null) ampEl.value = String(r.amplitude);
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
                renderLogicalSegments('recipe-logical-segments-list', window._recipeLogicalSegments, 'recipe-logical-total-time', 'recipe');
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
})();
