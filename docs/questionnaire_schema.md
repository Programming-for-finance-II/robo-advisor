# Questionnaire Schema — AI Robo-Advisor Risk Profiler
**Version:** 1.0  
**Methodology:** Grable & Lytton (1999) Risk Tolerance Scale  
**Output:** profile_label ∈ {CONSERVATIVE, MODERATE, AGGRESSIVE} + confidence score  

---

## Scoring

| Total Score | Profile Label | Confidence |
|---|---|---|
| 0–7 | CONSERVATIVE | 1.0 |
| 8–9 | CONSERVATIVE | 0.7 — borderline |
| 10–11 | MODERATE | 0.7 — borderline |
| 12–17 | MODERATE | 1.0 |
| 18–19 | MODERATE | 0.7 — borderline |
| 20–21 | AGGRESSIVE | 0.7 — borderline |
| 22–30 | AGGRESSIVE | 1.0 |

**Override rule:** if Q7 = a) → profile is capped at CONSERVATIVE regardless of total score.  
**low_confidence_flag = True** when confidence = 0.7.

---

## Section A — Who You Are Financially

**Q1. How old are you?**
- a) Over 60 → 0
- b) 46–60 → 1
- c) 30–45 → 2
- d) Under 30 → 3

*Rationale: age is a proxy for residual time horizon and capacity to recover from losses. Younger investors can afford greater short-term volatility because they have more time to compound and recover (Grable & Lytton 1999; SCF variable: AGE).*

---

**Q2. Thinking about your current financial situation, which best describes your household income?**
- a) Money is tight — I cover essentials but have little left over at the end of the month. → 0
- b) I'm comfortable — I meet my needs and manage to save something occasionally. → 1
- c) I'm in a solid position — I save regularly and have financial flexibility. → 2
- d) I have significant disposable income beyond my living expenses. → 3

*Rationale: measures the capacity to absorb losses without impact on lifestyle. Higher income allows greater risk-taking without threatening basic financial stability (Grable & Lytton 1999; MiFID II financial situation assessment; SCF variable: INCOME).*

---

**Q3. Suppose a major setback happens. If you had to live off your savings starting tomorrow, how many months could you cover your expenses?**
- a) Less than 3 months → 0
- b) 3–6 months → 1
- c) 6–12 months → 2
- d) More than 12 months → 3

*Rationale: measures real financial cushion rather than declared income. Investors with limited liquid reserves cannot afford portfolio volatility, as they may be forced to liquidate at unfavourable times (SCF variables: LIQUIDITY, SAVRES).*

---

**Q4. Do you have financial dependents — people who rely on your income to cover their living expenses?**
- a) No, I have no financial dependents. → 3
- b) Yes, one dependent (partner, child, or other). → 2
- c) Yes, two or three dependents. → 1
- d) Yes, four or more dependents. → 0

*Rationale: the number of financial dependents reduces risk capacity by increasing mandatory outflows and constraining available liquidity. A larger household has less margin to absorb sustained portfolio drawdowns (SCF variables: KIDS, FAMSIZE).*

---

## Section B — How You Invest

**Q5. How would you describe your investment experience?**
- a) None — I have never invested. → 0
- b) Basic — savings accounts or government bonds only. → 1
- c) Intermediate — I have invested in mutual funds or ETFs. → 2
- d) Advanced — I actively trade stocks, options, or other complex instruments. → 3

*Rationale: prior investment experience reduces emotional bias and increases the ability to tolerate short-term volatility without panic-driven decisions. Behavioural composure under stress is strongly correlated with hands-on market experience (SCF variable: SAVED).*

---

**Q6. Regardless of your investment experience, how would you rate your theoretical financial knowledge?**
- a) Very limited — I find financial topics confusing. → 0
- b) Basic — I understand how savings accounts and bonds work. → 1
- c) Intermediate — I'm comfortable with concepts like ETFs, diversification, and volatility. → 2
- d) Advanced — I understand derivatives, leverage, and portfolio construction strategies. → 3

*Rationale: theoretical financial literacy is an independent predictor of risk tolerance even in the absence of practical experience (Guiso, Sapienza & Zingales 2018; SCF variable: KNOWL). Combined with Q5, this question identifies asymmetric profiles — investors who understand risk intellectually but have never experienced it, or those who have invested without fully understanding the instruments.*

---

**Q7. What is the primary purpose of this investment — and when do you expect to need this money?**
- a) Safety net — I may need this money at any time, within months. → 0
- b) A specific goal within the next 5 years (house, education, major purchase). → 1
- c) Long-term wealth building or retirement — I won't need this for at least 10 years. → 2
- d) Aggressive growth — this is surplus capital with no planned withdrawal date. → 3

*Rationale: investment objective directly constrains the acceptable time horizon and risk profile under MiFID II suitability requirements (Art. 25). Short-term goals are incompatible with high-volatility instruments regardless of declared risk appetite. Override rule: if Q7 = a), the final profile is capped at CONSERVATIVE irrespective of total score.*

---

## Section C — How You React

**Q8. You check your portfolio and it has lost 20% of its value in the past month. What do you do?**
- a) "I cut my losses immediately — I sell everything and move to something safer. I can't watch it keep falling." → 0
- b) "I reduce my exposure — maybe I've missed something and the picture has changed. I sell part of it to limit the damage, but I don't exit completely." → 1
- c) "I hold my position and wait. Markets recover — panic selling is the worst thing you can do." → 2
- d) "This is an opportunity. I buy more at a discount and increase my position." → 3

*Rationale: measures immediate behavioural response to a concrete loss scenario. First-person framing reduces social desirability bias compared to abstract hypothetical questions. Immediate reaction to drawdown is one of the strongest short-term predictors of risk profile in Grable & Lytton (1999) and is directly observable as behaviour in the SCF (variable: RISKTOL).*

---

**Q9. Your portfolio drops 30% over 3 months. Assuming you decide to hold, how long are you willing to wait for a full recovery before reconsidering your strategy?**
- a) "A few months at most — if it hasn't bounced back, something is wrong." → 0
- b) "Up to 6 months — I can sit with the discomfort, but not indefinitely." → 1
- c) "One to three years — I understand recoveries take time." → 2
- d) "As long as it takes. If the fundamentals are sound, I don't have an exit deadline." → 3

*Rationale: measures temporal loss composure, distinct from immediate reaction (Q8). This dimension captures the investor's ability to sustain a drawdown over an extended period — the most discriminating single factor in Grable & Lytton (1999). Historically validated against real bear market behaviour in the dot-com bust (2000–2003) and the Global Financial Crisis (2008–2009).*

---

**Q10. Which investment profile fits you best over a 10-year horizon?**
- a) "The thought of losing any part of my savings worries me more than missing out on gains. I'd lock in a guaranteed +2% per year — modest, but no surprises." → 0
- b) "Mostly stable — I accept minor fluctuations for modest gains above inflation." → 1
- c) "Balanced — I accept significant swings in exchange for stronger long-term returns." → 2
- d) "Aggressive — I'm comfortable with large losses if the potential upside is high." → 3

*Rationale: self-assessed risk tolerance as an explicit final statement. Positioned last because at this point the respondent has already processed concrete loss and gain scenarios (Q8, Q9), reducing the social desirability bias that typically inflates self-reported risk appetite when asked cold. Validated as an independent predictor in Grable & Lytton (1999) and Guiso et al. (2018).*

---

## References

- Grable, J. E., & Lytton, R. H. (1999). Financial risk tolerance revisited: The development of a risk assessment instrument. *Financial Services Review*, 8(3), 163–181.
- Guiso, L., Sapienza, P., & Zingales, L. (2018). Time-varying risk aversion. *Journal of Financial Economics*, 128(3), 403–421.
- Federal Reserve Board (2022). *Survey of Consumer Finances*. Washington, D.C.
- MiFID II Directive 2014/65/EU, Article 25 — Suitability and appropriateness assessment.
