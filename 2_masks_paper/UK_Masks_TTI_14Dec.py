'''
UK scenarios for evaluating effectivness of masks
'''

import sciris as sc
import covasim as cv
import pylab as pl
import numpy as np
import matplotlib as mplt

########################################################################
# Settings and initialisation
########################################################################
# Check version
cv.check_version('2.0.0')
cv.git_info('covasim_version.json')

# Saving and plotting settings
do_plot = 0
do_save = 0
save_sim = 1
do_show = 0
verbose = 1
seed    = 1
n_runs = 200
to_plot = sc.objdict({
    'Cumulative diagnoses': ['cum_diagnoses'],
    'Cumulative infections': ['cum_infections'],
    'New infections': ['new_infections'],
    'Daily diagnoses': ['new_diagnoses'],
    'Cumulative deaths': ['cum_deaths'],
    'Cumulative critical': ['cum_critical'],
})

# Define what to run
runoptions = ['quickfit', # Does a quick preliminary calibration. Quick to run, ~30s
              'fullfit',  # Searches over parameters and seeds (10,000 runs) and calculates the mismatch for each. Slow to run: ~1hr
              'finialisefit', # Filters the 10,000 runs from the previous step, selects the best-fitting ones, and runs these
              'scens', # Takes the best-fitting runs and projects these forward under different mask and TTI assumptions
              ]
whattorun = runoptions[2] #Select which of the above to run

# Filepaths
data_path = '../UK_Covid_cases_august28.xlsx'
resfolder = 'results'

# Important dates
start_day = '2020-01-21'
end_day = '2021-03-31'
data_end = '2020-08-28' # Final date for calibration


########################################################################
# Create the baseline simulation
########################################################################

def make_sim(seed, beta, calibration=True, future_symp_test=None, scenario=None, end_day=None):

    # Set the parameters
    total_pop    = 67.86e6 # UK population size
    pop_size     = 100e3 # Actual simulated population
    pop_scale    = int(total_pop/pop_size)
    pop_type     = 'hybrid'
    pop_infected = 1500
    beta         = beta
    asymp_factor = 2
    contacts     = {'h':3.0, 's':20, 'w':20, 'c':20}
    if end_day is None: end_day = '2021-03-31'

    pars = sc.objdict(
        pop_size     = pop_size,
        pop_infected = pop_infected,
        pop_scale    = pop_scale,
        pop_type     = pop_type,
        start_day    = start_day,
        end_day      = end_day,
        beta         = beta,
        asymp_factor = asymp_factor,
        contacts     = contacts,
        rescale      = True,
        rand_seed    = seed,
    )

    sim = cv.Sim(pars=pars, datafile=data_path, location='uk')
    sim['prognoses']['sus_ORs'][0] = 1.0 # ages 20-30
    sim['prognoses']['sus_ORs'][1] = 1.0 # ages 20-30

    # ADD BETA INTERVENTIONS
    beta_past  = sc.odict({'2020-02-14': [1.00, 1.00, 0.90, 0.90, ],
                           '2020-03-16': [1.00, 0.90, 0.80, 0.80, ],
                           '2020-03-23': [1.29, 0.02, 0.20, 0.20, ],
                           '2020-04-30': [1.29, 0.02, 0.20, 0.20, ],
                           '2020-05-15': [1.29, 0.02, 0.20, 0.20, ],
                           '2020-06-01': [1.00, 0.23, 0.40, 0.40, ],
                           '2020-06-15': [1.00, 0.38, 0.50, 0.50, ],
                           '2020-07-22': [1.29, 0.00, 0.425, 0.49, ],
                           })

    if not calibration:
        if scenario == 'phased-june-full-sep-masks15':
            sbv1, sbv2, wbv1, wbv2, cbv1, cbv2 = 0.765, 1.00, 0.595, 0.425, 0.765, 0.595
        elif scenario == 'phased-june-full-sep-masks30':
            sbv1, sbv2, wbv1, wbv2, cbv1, cbv2 = 0.63,  0.70, 0.49,  0.35,  0.63,  0.49
        elif scenario == 'phased-june-full-sep-masks15_notschools':
            sbv1, sbv2, wbv1, wbv2, cbv1, cbv2 = 0.90,  0.90, 0.595, 0.425, 0.765, 0.595
        elif scenario == 'phased-june-full-sep-masks30_notschools':
            sbv1, sbv2, wbv1, wbv2, cbv1, cbv2 = 0.90,  0.70, 0.49,  0.35,  0.63,  0.49

        beta_scens = sc.odict({'2020-09-02': [1.00, sbv1, wbv1, cbv1],
                               '2020-10-28': [1.00, 0.00, wbv2, cbv2],
                               '2020-11-01': [1.00, sbv1, wbv1, cbv1],
                               '2020-12-23': [1.00, 0.00, wbv2, cbv2],
                               '2021-01-03': [1.00, sbv1, wbv1, cbv1],
                               '2021-02-17': [1.00, 0.00, wbv2, cbv2],
                               '2021-02-21': [1.00, sbv1, wbv1, cbv1],
                               '2021-04-06': [1.00, 0.00, wbv2, cbv2],
                               '2021-04-17': [1.00, sbv2, wbv1, cbv1]
                              })

        beta_dict = sc.mergedicts(beta_past, beta_scens)
    else:
        beta_dict = beta_past

    h_beta = cv.change_beta(days=beta_dict.keys(), changes=[c[0] for c in beta_dict.values()], layers='h')
    s_beta = cv.change_beta(days=beta_dict.keys(), changes=[c[1] for c in beta_dict.values()], layers='s')
    w_beta = cv.change_beta(days=beta_dict.keys(), changes=[c[2] for c in beta_dict.values()], layers='w')
    c_beta = cv.change_beta(days=beta_dict.keys(), changes=[c[3] for c in beta_dict.values()], layers='c')

    interventions = [h_beta, w_beta, s_beta, c_beta]

    # ADD TEST AND TRACE INTERVENTIONS
    tc_day = sim.day('2020-03-16') #intervention of some testing (tc) starts on 16th March and we run until 1st April when it increases
    te_day = sim.day('2020-04-01') #intervention of some testing (te) starts on 1st April and we run until 1st May when it increases
    tt_day = sim.day('2020-05-01') #intervention of increased testing (tt) starts on 1st May
    tti_day= sim.day('2020-06-01') #intervention of tracing and enhanced testing (tti) starts on 1st June
    tti_day_july= sim.day('2020-07-01') #intervention of tracing and enhanced testing (tti) at different levels starts on 1st July
    tti_day_august= sim.day('2020-08-01') #intervention of tracing and enhanced testing (tti) at different levels starts on 1st August
    tti_day_sep= sim.day('2020-09-01') #intervention of tracing and enhanced testing (tti) at different levels starts on 1st August

    s_prob_april = 0.008
    s_prob_may   = 0.03
    s_prob_june = 0.02
    s_prob_july = 0.02
    s_prob_august = 0.02
    if future_symp_test is None: future_symp_test = s_prob_august
    t_delay       = 1.0

    iso_vals = [{k:0.1 for k in 'hswc'}]

    #tracing level at 42.35% in June; 47.22% in July
    t_eff_june   = 0.42
    t_eff_july   = 0.47
    t_probs_june = {k:t_eff_june for k in 'hwsc'}
    t_probs_july = {k:t_eff_july for k in 'hwsc'}
    trace_d_1      = {'h':0, 's':1, 'w':1, 'c':2}

    #testing and isolation intervention
    interventions += [
        cv.test_prob(symp_prob=0.0075, asymp_prob=0.0, symp_quar_prob=0.0, start_day=tc_day, end_day=te_day-1, test_delay=t_delay),
        cv.test_prob(symp_prob=s_prob_april, asymp_prob=0.0, symp_quar_prob=0.0, start_day=te_day, end_day=tt_day-1, test_delay=t_delay),
        cv.test_prob(symp_prob=s_prob_may, asymp_prob=0.00075, symp_quar_prob=0.0, start_day=tt_day, end_day=tti_day-1, test_delay=t_delay),
        cv.test_prob(symp_prob=s_prob_june, asymp_prob=0.00075, symp_quar_prob=0.0, start_day=tti_day, end_day=tti_day_july-1, test_delay=t_delay),
        cv.test_prob(symp_prob=s_prob_july, asymp_prob=0.00075, symp_quar_prob=0.0, start_day=tti_day_july, end_day=tti_day_august-1, test_delay=t_delay),
        cv.test_prob(symp_prob=s_prob_august, asymp_prob=0.00075, symp_quar_prob=0.0, start_day=tti_day_august, end_day=tti_day_sep-1, test_delay=t_delay),
        cv.test_prob(symp_prob=future_symp_test, asymp_prob=0.00075, symp_quar_prob=0.0, start_day=tti_day_sep, test_delay=t_delay),
        cv.dynamic_pars({'iso_factor': {'days': te_day, 'vals': iso_vals}}),
        cv.contact_tracing(trace_probs=t_probs_june, trace_time=trace_d_1, start_day=tti_day, end_day=tti_day_july-1),
        cv.contact_tracing(trace_probs=t_probs_july, trace_time=trace_d_1, start_day=tti_day_july),
      ]

    # Finally, update the parameters
    sim.update_pars(interventions=interventions)
    for intervention in sim['interventions']:
        intervention.do_plot = False

    sim.initialize()

    return sim


########################################################################
# Run calibration and scenarios
########################################################################
if __name__ == '__main__':

    betas = [i / 10000 for i in range(72, 77, 1)]

    # Quick calibration
    if whattorun=='quickfit':
        s0 = make_sim(seed=1, beta=0.0075, end_day=data_end)
        sims = []
        for seed in range(6):
            sim = s0.copy()
            sim['rand_seed'] = seed
            sim.set_seed()
            sim.label = f"Sim {seed}"
            sims.append(sim)
        msim = cv.MultiSim(sims)
        msim.run()
        msim.reduce()
        if do_plot:
            msim.plot(to_plot=to_plot, do_save=True, do_show=False, fig_path=f'uk.png',
                      legend_args={'loc': 'upper left'}, axis_args={'hspace': 0.4}, interval=50)

    # Full parameter/seed search
    elif whattorun=='fullfit':
        fitsummary = []
        for beta in betas:
            sc.blank()
            print('---------------\n')
            print(f'Beta: {beta}... ')
            print('---------------\n')
            s0 = make_sim(seed=1, beta=beta, end_day=data_end)
            sims = []
            for seed in range(n_runs):
                sim = s0.copy()
                sim['rand_seed'] = seed
                sim.set_seed()
                sim.label = f"Sim {seed}"
                sims.append(sim)
            msim = cv.MultiSim(sims)
            msim.run()
            fitsummary.append([sim.compute_fit().mismatch for sim in msim.sims])

        sc.saveobj(f'{resfolder}/fitsummary.obj',fitsummary)

    # Run calibration with best-fitting seeds and parameters
    elif whattorun=='finialisefit':
        sims = []
        fitsummary = sc.loadobj(f'{resfolder}/fitsummary.obj')
        for bn, beta in enumerate(betas):
            goodseeds = [i for i in range(n_runs) if fitsummary[bn][i] < 126]
            sc.blank()
            print('---------------\n')
            print(f'Beta: {beta}, goodseeds: {len(goodseeds)}')
            print('---------------\n')
            if len(goodseeds) > 0:
                s0 = make_sim(seed=1, beta=beta, end_day=data_end)
                for seed in goodseeds:
                    sim = s0.copy()
                    sim['rand_seed'] = seed
                    sim.set_seed()
                    sim.label = f"Sim {seed}"
                    sims.append(sim)

        msim = cv.MultiSim(sims)
        msim.run()

        if save_sim:
            msim.save(f'{resfolder}/uk_sim.obj')
        if do_plot:
            msim.reduce()
            msim.plot(to_plot=to_plot, do_save=do_save, do_show=False, fig_path=f'uk.png',
                      legend_args={'loc': 'upper left'}, axis_args={'hspace': 0.4}, interval=50)



# Define scenarios
#scenario = ['phased-june-full-sep-masks15', 'phased-june-full-sep-masks30', 'phased-june-full-sep-masks15_notschools', 'phased-june-full-sep-masks30_notschools'][3] # Set a number to pick a scenario from the available options
#tti_scen = ['current', 'optimal_masks15', 'optimal_masks30', 'optimal_masks15_notschools', 'optimal_masks30_notschools'][0] # Ditt0
