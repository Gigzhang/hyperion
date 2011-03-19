module setup

  use core_lib

  use grid_physics, only : setup_grid_physics
  use grid_geometry, only : setup_grid_geometry
  use sources
  use dust_main
  use type_dust
  use lib_conf
  use binned_images
  use peeled_images
  use settings

  implicit none
  save

  private
  public :: setup_initial
  public :: setup_final_iteration

contains

  subroutine setup_initial(input_handle)

    implicit none

    integer(hid_t),intent(in) :: input_handle
    integer(hid_t) :: g_dust, g_geometry, g_physics, g_sources, g_output
    integer :: physics_io_bytes

    call hdf5_read_keyword(input_handle, '/', 'monochromatic', use_exact_nu)
    call hdf5_read_keyword(input_handle, '/', 'raytracing', use_raytracing)

    call hdf5_read_keyword(input_handle, '/', 'n_stats', n_stats)

    call hdf5_read_keyword(input_handle, '/', 'n_inter_max', n_inter_max)
    call hdf5_read_keyword(input_handle, '/', 'n_reabs_max', n_reabs_max)

    call hdf5_read_keyword(input_handle, '/', 'pda', use_pda)
    call hdf5_read_keyword(input_handle, '/', 'mrw', use_mrw)

    if(use_mrw) then
       call hdf5_read_keyword(input_handle, '/', 'mrw_gamma', mrw_gamma)
       call hdf5_read_keyword(input_handle, '/', 'n_inter_mrw_max', n_mrw_max)
    end if

    call hdf5_read_keyword(input_handle, '/', 'kill_on_absorb', kill_on_absorb)
    call hdf5_read_keyword(input_handle, '/', 'forced_first_scattering', forced_first_scattering)

    if(hdf5_exists_keyword(input_handle, '/', 'sample_sources_evenly')) then
       call hdf5_read_keyword(input_handle, '/', 'sample_sources_evenly', sample_sources_evenly)
    else
       sample_sources_evenly = .false.
    end if

    ! DUST

    g_dust = hdf5_open_group(input_handle, '/Dust')
    call setup_dust(g_dust)
    call hdf5_close_group(g_dust)

    if(n_dust==0) then
       call warn("main", "no dust present, so skipping temperature iterations")
       n_lucy_iter=0
       if(use_exact_nu) n_last_photons_dust = 0
       if(use_raytracing) n_raytracing_photons_dust = 0
    else
       call hdf5_read_keyword(input_handle, '/', 'n_lucy_iter', n_lucy_iter)
       if(n_lucy_iter > 0) then
          call hdf5_read_keyword(input_handle, '/', 'n_lucy_photons', n_lucy_photons)
          if(n_lucy_photons==0) call error("setup_initial", "Number of temperature iterations is non-zero, but number of temperature photons is zero")
       else
          n_lucy_photons = 0
       end if
       if(use_exact_nu) call hdf5_read_keyword(input_handle, '/', 'n_last_photons_dust', n_last_photons_dust)
       if(use_raytracing) call hdf5_read_keyword(input_handle, '/', 'n_ray_photons_dust', n_raytracing_photons_dust)
    end if

    ! GRID

    g_geometry = hdf5_open_group(input_handle, '/Grid/Geometry')
    call setup_grid_geometry(g_geometry)
    call hdf5_close_group(g_geometry)

    g_physics = hdf5_open_group(input_handle, '/Grid/Physics')
    call setup_grid_physics(g_physics, use_mrw, use_pda)
    call hdf5_close_group(g_physics)

    call hdf5_read_keyword(input_handle, '/', 'physics_io_bytes', physics_io_bytes)

    select case(physics_io_bytes)
    case(4)
       physics_io_type = sp
    case(8)
       physics_io_type = dp
    case default
       call error("setup_initial", "unexpected value of physics_io_bytes (should be 4 or 8)")
    end select

    ! FREQUENCIES

    if(use_exact_nu) then
       call hdf5_table_read_column_auto(input_handle, 'Frequencies', 'nu', frequencies)
    end if

    ! SOURCES

    g_sources = hdf5_open_group(input_handle, '/Sources')
    call setup_sources(g_sources)
    call hdf5_close_group(g_sources)

    ! If no sources have been set up, give an error if we are not in raytracing only mode
    if(n_sources == 0) then
       if(n_lucy_iter > 0) call error("setup_initial","no sources set up - need sources for temperature iteration")
       if(use_exact_nu) then
          n_last_photons_sources = 0
       else
          if(n_last_photons > 0) call error("setup_initial","no sources set up - need sources for last iteration")
       end if
       if(use_raytracing) n_raytracing_photons_sources = 0
    else
       if(use_exact_nu) then
          call hdf5_read_keyword(input_handle, '/', 'n_last_photons_sources', n_last_photons_sources)
       else
          call hdf5_read_keyword(input_handle, '/', 'n_last_photons', n_last_photons)
       end if
       if(use_raytracing) call hdf5_read_keyword(input_handle, '/', 'n_ray_photons_sources', n_raytracing_photons_sources)
    end if

    ! OUTPUT

    g_output = hdf5_open_group(input_handle, '/Output')  

    call hdf5_read_keyword(g_output, '.', 'output_temperature', output_temperature)

    if(trim(output_temperature).ne.'all' &
         & .and.trim(output_temperature).ne.'last' &
         & .and.trim(output_temperature).ne.'none') &
         & call error("setup_initial", "output_temperature should be one of all/last/none")

    call hdf5_read_keyword(g_output, '.', 'output_density', output_density)

    if(trim(output_density).ne.'all' &
         & .and.trim(output_density).ne.'last' &
         & .and.trim(output_density).ne.'none') &
         & call error("setup_initial","output_density should be one of all/last/none")

    call hdf5_read_keyword(g_output, '.', 'output_density_diff', output_density_diff)

    if(trim(output_density_diff).ne.'all' &
         & .and.trim(output_density_diff).ne.'last' &
         & .and.trim(output_density_diff).ne.'none') &
         & call error("setup_initial","output_density_diff should be one of all/last/none")

    call hdf5_read_keyword(g_output, '.', 'output_specific_energy_abs', output_specific_energy_abs)

    if(trim(output_specific_energy_abs).ne.'all' &
         & .and.trim(output_specific_energy_abs).ne.'last' &
         & .and.trim(output_specific_energy_abs).ne.'none') &
         & call error("setup_initial","output_specific_energy_abs should be one of all/last/none")

    call hdf5_read_keyword(g_output, '.', 'output_n_photons', output_n_photons)

    if(trim(output_n_photons).ne.'all' &
         & .and.trim(output_n_photons).ne.'last' &
         & .and.trim(output_n_photons).ne.'none') &
         & call error("setup_initial","output_n_photons should be one of all/last/none")

    call hdf5_close_group(g_output)

    ! TEMPERATURE CONVERGENCE
    if(n_lucy_iter > 0) then
       call hdf5_read_keyword(input_handle, '/', 'check_convergence', check_convergence)
       if(check_convergence) then
          call hdf5_read_keyword(input_handle, '/', 'convergence_absolute', convergence_absolute)
          call hdf5_read_keyword(input_handle, '/', 'convergence_relative', convergence_relative)
          call hdf5_read_keyword(input_handle, '/', 'convergence_percentile', convergence_percentile)
       end if
    end if

  end subroutine setup_initial

  subroutine setup_final_iteration(input_handle)

    implicit none

    integer(hid_t),intent(in) :: input_handle
    integer :: n_peeled
    integer(hid_t) :: g_binned, g_peeled
    character(len=255),allocatable :: group_names(:)

    ! Read configuration for binned images
    g_binned = hdf5_open_group(input_handle, '/Output/Binned')   
    call hdf5_list_groups(g_binned, '.', group_names)

    if(size(group_names)==0) then
       make_binned_images = .false.
    else if(size(group_names)==1) then
       make_binned_images = .true.
    else
       call error("setup_final_iteration","can't have more than one binned image group")
    end if

    if(make_binned_images) then
       if(use_exact_nu) call error("setup_final_iteration","can't use binned images in exact wavelength mode")
       if(forced_first_scattering) call error("setup_final_iteration", "can't use binned images with forced first scattering")
       call binned_images_setup(g_binned, group_names(1))
    end if

    ! Read configuration for peeloff images
    g_peeled = hdf5_open_group(input_handle, '/Output/Peeled')   
    call hdf5_list_groups(g_peeled, '.', group_names)
    n_peeled = size(group_names)
    make_peeled_images = n_peeled > 0

    if(make_peeled_images) then
       if(allocated(frequencies)) then
          call peeled_images_setup(g_peeled, group_names, use_raytracing, use_exact_nu, frequencies)
       else
          call peeled_images_setup(g_peeled, group_names, use_raytracing, use_exact_nu)
       end if
    end if

  end subroutine setup_final_iteration

end module setup
