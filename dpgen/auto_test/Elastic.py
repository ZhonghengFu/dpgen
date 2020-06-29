from dpgen import dlog
from dpgen.auto_test.Property import Property
from dpgen.auto_test.refine import make_refine
from pymatgen.core.structure import Structure
from pymatgen.analysis.elasticity.strain import DeformedStructureSet, Strain
from pymatgen.analysis.elasticity.stress import Stress
from pymatgen.analysis.elasticity.elastic import ElasticTensor
from monty.serialization import loadfn, dumpfn
import os
from pymatgen.io.vasp import Incar, Kpoints
from dpgen.generator.lib.vasp import incar_upper
import dpgen.auto_test.lib.vasp as vasp


class Elastic(Property):
    def __init__(self,
                 parameter):
        self.parameter = parameter
        default_norm_def = 2e-3
        default_shear_def = 5e-3
        self.norm_deform = parameter.get('norm_deform', default_norm_def)
        self.shear_deform = parameter.get('shear_deform', default_shear_def)
        parameter['cal_type'] = parameter.get('cal_type', 'relaxation')
        self.cal_type = parameter['cal_type']
        default_cal_setting = {"relax_pos": True,
                               "relax_shape": False,
                               "relax_vol": False}
        parameter['cal_setting'] = parameter.get('cal_setting', default_cal_setting)
        self.cal_setting = parameter['cal_setting']
        parameter['reprod-opt'] = False
        self.reprod = parameter['reprod-opt']
        self.parameter = parameter

    def make_confs(self,
                   path_to_work,
                   path_to_equi,
                   refine=False):
        path_to_work = os.path.abspath(path_to_work)
        if os.path.exists(path_to_work):
            dlog.warning('%s already exists' % path_to_work)
        else:
            os.makedirs(path_to_work)
        path_to_equi = os.path.abspath(path_to_equi)
        if 'start_confs_path' in self.parameter and os.path.exists(self.parameter['start_confs_path']):
            path_to_equi = os.path.abspath(self.parameter['start_confs_path'])

        task_list = []
        cwd = os.getcwd()

        norm_def = self.norm_deform
        shear_def = self.shear_deform
        norm_strains = [-norm_def, -0.5 * norm_def, 0.5 * norm_def, norm_def]
        shear_strains = [-shear_def, -0.5 * shear_def, 0.5 * shear_def, shear_def]

        equi_contcar = os.path.join(path_to_equi, 'CONTCAR')
        if not os.path.exists(equi_contcar):
            raise RuntimeError("please do relaxation first")

        ss = Structure.from_file(equi_contcar)
        dfm_ss = DeformedStructureSet(ss,
                                      symmetry=False,
                                      norm_strains=norm_strains,
                                      shear_strains=shear_strains)
        n_dfm = len(dfm_ss)

        os.chdir(path_to_work)
        if os.path.isfile('POSCAR'):
            os.remove('POSCAR')
        os.symlink(os.path.relpath(equi_contcar), 'POSCAR')
        #           task_poscar = os.path.join(output, 'POSCAR')

        # stress, deal with unsupported stress in dpdata
        #with open(os.path.join(path_to_equi, 'result.json')) as fin:
        #    equi_result = json.load(fin)
        #equi_stress = np.array(equi_result['stress']['data'])[-1]
        equi_result = loadfn(os.path.join(path_to_equi, 'result.json'))
        equi_stress = equi_result['stress'][-1]
        dumpfn(equi_stress, 'equi.stress.json', indent=4)

        if refine:
            print('elastic refine starts')
            task_list = make_refine(self.parameter['init_from_suffix'],
                                    self.parameter['output_suffix'],
                                    path_to_work)
            idid = -1
            for ii in task_list:
                idid += 1
                os.chdir(ii)
                if os.path.isfile('strain.json'):
                    os.remove('strain.json')

                # record strain
                df = Strain.from_deformation(dfm_ss.deformations[idid])
                dumpfn(df.as_dict(), 'strain.json', indent=4)
                #os.symlink(os.path.relpath(
                #    os.path.join((re.sub(self.parameter['output_suffix'], self.parameter['init_from_suffix'], ii)),
                #                 'strain.json')),
                #           'strain.json')
            os.chdir(cwd)
        else:
            print('gen with norm ' + str(norm_strains))
            print('gen with shear ' + str(shear_strains))
            for ii in range(n_dfm):
                output_task = os.path.join(path_to_work, 'task.%06d' % ii)
                os.makedirs(output_task, exist_ok=True)
                os.chdir(output_task)
                for jj in ['INCAR', 'POTCAR', 'POSCAR', 'conf.lmp', 'in.lammps']:
                    if os.path.exists(jj):
                        os.remove(jj)
                task_list.append(output_task)
                dfm_ss.deformed_structures[ii].to('POSCAR', 'POSCAR')
                # record strain
                df = Strain.from_deformation(dfm_ss.deformations[ii])
                dumpfn(df.as_dict(), 'strain.json', indent=4)
            os.chdir(cwd)
        return task_list

    def post_process(self, task_list):
        cwd = os.getcwd()
        poscar_start = os.path.abspath(os.path.join(task_list[0], '..', 'POSCAR'))
        os.chdir(os.path.join(task_list[0], '..'))
        if os.path.isfile(os.path.join(task_list[0], 'INCAR')):
            incar = incar_upper(Incar.from_file(os.path.join(task_list[0], 'INCAR')))
            kspacing = incar.get('KSPACING')
            kgamma = incar.get('KGAMMA', False)
            ret = vasp.make_kspacing_kpoints(poscar_start, kspacing, kgamma)
            kp = Kpoints.from_string(ret)
            if os.path.isfile('KPOINTS'):
                os.remove('KPOINTS')
            kp.write_file("KPOINTS")
            os.chdir(cwd)
            kpoints_universal = os.path.abspath(os.path.join(task_list[0], '..', 'KPOINTS'))
            for ii in task_list:
                if os.path.isfile(os.path.join(ii, 'KPOINTS')):
                    os.remove(os.path.join(ii, 'KPOINTS'))
                os.chdir(ii)
                os.symlink(os.path.relpath(kpoints_universal), 'KPOINTS')
        os.chdir(cwd)

    def task_type(self):
        return self.parameter['type']

    def task_param(self):
        return self.parameter

    def _compute_lower(self,
                       output_file,
                       all_tasks,
                       all_res):
        output_file = os.path.abspath(output_file)
        res_data = {}
        ptr_data = os.path.dirname(output_file) + '\n'
        equi_stress = Stress(loadfn(os.path.join(os.path.dirname(output_file), 'equi.stress.json')))
        lst_strain = []
        lst_stress = []
        for ii in all_tasks:
            strain = loadfn(os.path.join(ii, 'strain.json'))
            # stress, deal with unsupported stress in dpdata
            #with open(os.path.join(ii, 'result_task.json')) as fin:
            #    task_result = json.load(fin)
            #stress = np.array(task_result['stress']['data'])[-1]
            stress = loadfn(os.path.join(ii, 'result_task.json'))['stress'][-1]
            lst_strain.append(strain)
            lst_stress.append(Stress(stress * -1000))

        et = ElasticTensor.from_independent_strains(lst_strain, lst_stress, eq_stress=equi_stress, vasp=False)
        res_data['elastic_tensor'] = []
        for ii in range(6):
            for jj in range(6):
                res_data['elastic_tensor'].append(et.voigt[ii][jj] / 1e4)
                ptr_data += "%7.2f " % (et.voigt[ii][jj] / 1e4)
            ptr_data += '\n'

        BV = et.k_voigt / 1e4
        GV = et.g_voigt / 1e4
        EV = 9 * BV * GV / (3 * BV + GV)
        uV = 0.5 * (3 * BV - 2 * GV) / (3 * BV + GV)

        res_data['BV'] = BV
        res_data['GV'] = GV
        res_data['EV'] = EV
        res_data['uV'] = uV
        ptr_data += "# Bulk   Modulus BV = %.2f GPa\n" % BV
        ptr_data += "# Shear  Modulus GV = %.2f GPa\n" % GV
        ptr_data += "# Youngs Modulus EV = %.2f GPa\n" % EV
        ptr_data += "# Poission Ratio uV = %.2f\n " % uV

        dumpfn(res_data, output_file, indent=4)

        return res_data, ptr_data