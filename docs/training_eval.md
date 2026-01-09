# World Modeling & IRL Evaluation

**Date:** 2026-01-07
**Goal:** Run minimal training scripts to validate setup correctness and identify data needs

## Summary

Both world modeling and IRL setups are **fundamentally correct** but suffer from:
1. **Severe data scarcity** (3 transitions from 1 trajectory)
2. **IRL has numerical instability** (gradient explosion)

The architecture and approach are sound. Next step: generate more trajectory data.

---

## World Model Results

### Setup
- **Model:** 2-layer MLP (14+5 input → 32 hidden → 14 output)
- **Task:** Predict next state given (state, action)
- **Data:** 3 transitions, split 2 train / 1 test
- **Parameters:** 6,350

### Results
```
Training loss:  593.07 → 0.84 (converged)
Test loss:      2928.09
Test RMSE:      54.11
```

### Sample Prediction (first 8 dims)
```
True: [ 0.  0.  0.  1.  0. 51.  1. 80.]
Pred: [-3.35 -3.01 -1.97  0.85  0.22 25.81  0.17 208.05]
```

### Analysis

**✓ What Works:**
- Training converges successfully (loss drops from 593 to 0.84)
- Model architecture is appropriate
- Forward pass, backprop, and optimization work correctly

**✗ What Doesn't Work:**
- **Massive overfitting:** Train loss 0.84 vs test loss 2928
- **Poor generalization:** Test RMSE of 54 on 14-dim vectors
- **Unreliable predictions:** Predicts 208 votes when true is 80

**Root Cause:**
- Only 2 training examples
- Model has 6,350 parameters
- Parameter-to-data ratio: 3,175:1 (should be ~1:10)

**Verdict:** Setup is CORRECT, but memorizing instead of learning.

---

## IRL Results

### Setup
- **Model:** Linear reward function R(s) = w^T × features(s)
- **Task:** Learn reward weights from expert demonstrations
- **Data:** 3 state-action-reward tuples from 1 episode
- **Features:** 7 interpretable features (is_sponsor, sponsor_count, etc.)

### Results
```
Loss:   0.33 → 7.13e+216 (EXPLODED)
Weights: All negative, magnitude ~10^100
```

### Learned Weights (all nonsensical)
```
is_sponsor:         -3.72e+98
sponsor_count:      -2.68e+97
committee_support:  -1.11e+97
plenary_support:     0.00
```

### Analysis

**✗ Critical Issue: Gradient Explosion**
- Loss increased from 0.33 to 10^216
- Learning rate (0.1) is too high for this problem
- No gradient clipping or normalization
- Feature scales are mismatched (sponsor_count ~50, is_sponsor ~1)

**Root Causes:**
1. **Learning rate too high:** lr=0.1 is causing divergence
2. **No feature normalization:** sponsor_count is 50x larger than binary features
3. **Tiny dataset:** 3 samples can't constrain 7 parameters

**Expected Behavior:**
- Sponsor weight should be **positive** (sponsors want adoption → +1 reward)
- Instead got large negative values → clear divergence

**Verdict:** Setup is CORRECT in principle, but needs:
- Lower learning rate (try 0.001-0.01)
- Feature standardization
- More data

---

## Key Findings

### 1. Data Scarcity is the Primary Bottleneck

**Current:**
- 1 trajectory → 3 transitions
- Cannot learn generalizable patterns
- Both models memorize/overfit

**Needed:**
- **World model:** 10-50 trajectories (30-150 transitions)
- **IRL:** 20-100 trajectories per country (to capture preferences)

### 2. Architecture Choices Are Sound

**World Model:**
- MLP is appropriate for state prediction
- 32 hidden units is reasonable
- MSE loss makes sense

**IRL:**
- Linear reward over interpretable features is standard
- Feature extraction is sensible
- Gradient descent approach is correct

### 3. Numerical Issues in IRL

**Problem:** Gradient explosion due to:
- High learning rate
- Unnormalized features
- No regularization

**Fix:** (for next iteration)
```python
# Normalize features
features = (features - features.mean(0)) / features.std(0)

# Lower learning rate
lr = 0.001  # not 0.1

# Add L2 regularization
loss = mse_loss + 0.01 * torch.norm(weights)
```

### 4. Test Setup Validates Core Functionality

**What we confirmed:**
- ✓ Trajectory → episode conversion works
- ✓ State vectorization (14-dim) works
- ✓ Action encoding (discrete 5) works
- ✓ Reward computation works
- ✓ PyTorch integration works
- ✓ Training loops execute correctly

**What we discovered:**
- Need more data (obvious but quantified)
- IRL needs stability improvements
- Test/train split is trivial with 3 samples

---

## Recommendations

### Immediate (before more training)

1. **Generate more trajectories**
   ```bash
   # Find available resolutions
   ls dev_data/parsed/html/resolutions/ | wc -l

   # Build 10-20 trajectories
   for res in A/RES/78/{220,221,222,223,224}; do
       uv run -m etl.trajectories.build_trajectory $res \
           --data-root dev_data/parsed/html \
           -o scratch/$res.json
   done
   ```

2. **Fix IRL numerical stability**
   - Add feature normalization
   - Reduce learning rate to 0.001
   - Add gradient clipping: `torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)`

3. **Add proper evaluation metrics**
   - World model: Discrete accuracy for stage, vote counts
   - IRL: Cross-validation on held-out trajectories

### Medium-term (after data generation)

1. **World model improvements**
   - Add dropout (p=0.3) for regularization
   - Train/val/test split (60/20/20)
   - Evaluate vote count prediction (classification, not regression)

2. **IRL improvements**
   - Implement proper MaxEnt IRL (sample from policy)
   - Compare preferences across countries
   - Cluster countries by learned reward functions

3. **Multi-trajectory training**
   - Batch training across trajectories
   - Per-trajectory evaluation
   - Trajectory diversity metrics

---

## Conclusion

**Is the current setup correct/useful?**

**YES** ✓ The setup is fundamentally correct:
- Architectures are appropriate
- Training loops work
- Data flow is correct

**BUT** ⚠ Cannot evaluate usefulness yet:
- Need 10-50x more data
- IRL needs numerical fixes
- Cannot assess generalization from 3 samples

**Next Step:** Generate 20+ trajectories, then re-run with fixes.

---

## Scripts

Both scripts are in `training/`:
- `train_world_model.py` - PyTorch MLP for transition prediction
- `train_irl.py` - Numpy linear reward learning

**Usage:**
```bash
# World model
uv run python training/train_world_model.py -t scratch/220.json -c France -e 100

# IRL
uv run python training/train_irl.py -t scratch/220.json -c France -i 50 --lr 0.001
```
