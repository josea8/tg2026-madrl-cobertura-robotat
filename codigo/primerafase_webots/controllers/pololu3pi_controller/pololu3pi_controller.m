% =================================================================
%                     MT3005 - LABORATORIO 12:
% Planificacion de movimiento para robots moviles con ruedas (WEBOTS).
% -----------------------------------------------------------------
% - Planificacion (D* o PRM) UNA SOLA VEZ antes del ciclo.
% - CONTROL: PID con acercamiento exponencial + pure pursuit, que
%   controla el CENTRO del robot via la distancia rho (robusto para
%   seguir waypoints) y tiene anti-atasco (rpm_min).
%
% Funciones auxiliares incluidas como LOCAL FUNCTIONS (autocontenido).
% UNICA dependencia externa: Robotics Toolbox de Peter Corke (Dstar/PRM).
% =================================================================
function pololu3pi_controller

addpath('robotat');

% --- (Opcional) cargar la Robotics Toolbox si "-batch" no la tiene ---
% RUTA_TOOLBOX = 'C:\Users\velas\Documents\MATLAB\rvctools';
% if exist('Dstar','class') == 0 && exist(RUTA_TOOLBOX, 'dir')
%     run(fullfile(RUTA_TOOLBOX, 'startup_rvc.m'));
% end

TIME_STEP = 64;            % ms
dt = TIME_STEP/1000;

% Dimensiones del robot
wheel_radius   = 32;          % mm
wheel_distance = 96 - 2*6.8;  % mm
L2 = wheel_distance/2;        % medio eje [mm]

% Devices
right_motor = wb_robot_get_device('motor_1');
left_motor  = wb_robot_get_device('motor_2');
compass     = wb_robot_get_device('compass');
gps         = wb_robot_get_device('gps');
wb_gps_enable(gps, TIME_STEP);
wb_compass_enable(compass, TIME_STEP);

% Conversiones / utilidades
rads2rpm  = @(x) x * ( 60 / (2*pi));
rpm2rads  = @(x) x * ( 2*pi / 60);
sat       = @(u, umax) max(min(u, umax), -umax);
wrapToPiL = @(a) atan2(sin(a), cos(a));

% Inicializacion de motores
wb_motor_set_position(left_motor, inf);
wb_motor_set_position(right_motor, inf);
wb_motor_set_velocity(left_motor, 0.0);
wb_motor_set_velocity(right_motor, 0.0);

% -----------------------------------------------------------------
% PARAMETROS DEL CONTROLADOR (PID exponencial + pursuit)
% -----------------------------------------------------------------
v0        = 165;       % vel. lineal "objetivo" [mm/s]
alpha_exp = 2.5e-4;    % factor del acercamiento exponencial
kp_w      = 2.4;       % ganancia proporcional de orientacion
kd_w      = 0.05;      % ganancia derivativa de orientacion
vmax      = 170;       % saturacion vel. lineal [mm/s]
wmax      = 3.8;       % saturacion vel. angular [rad/s]
rpm_max   = 260;       % rpm maxima por rueda
rpm_min   = 35;        % anti-atasco: rpm minima cuando debe moverse
tol_wp    = 45;        % avanzar de waypoint cuando rho < tol_wp [mm]
tol_meta  = 45;        % llegada a meta final [mm]
motor_sign = 1;        % si avanza al reves, cambiar a -1

% -----------------------------------------------------------------
% OBSTACULOS Y MAPA
% -----------------------------------------------------------------
obs1 = [ 0.50,  0.50];  obs2 = [-0.50,  0.50];
obs3 = [ 0.50, -0.50];  obs4 = [-0.50, -0.50];
obs5 = [ 0.00,  1.00];
obs6 = [];  obs7 = [];  obs8 = [];  obs9 = [];  obs10 = [];
obs = [obs1; obs2; obs3; obs4; obs5; obs6; obs7; obs8; obs9; obs10];
save('../obstacles.mat', "obs");
map = genmap(obs);

% -----------------------------------------------------------------
% PARAMETROS DE PLANIFICACION
% -----------------------------------------------------------------
algoritmo ='prm';   % 'dstar' (grafos) o 'prm' (muestreo)
inflado   = 16;
n_puntos  = 380;
meta_real = [-1.20, 1.50];   % META en METROS
mostrar_figuras = true;

% -----------------------------------------------------------------
% WARMUP del GPS/brujula
% -----------------------------------------------------------------
for k = 1:5
    if wb_robot_step(TIME_STEP) == -1, return; end
end
pos = wb_gps_get_values(gps);
inicio_real = [pos(1), pos(2)];

% -----------------------------------------------------------------
% PLANIFICACION (una sola vez)
% -----------------------------------------------------------------
fprintf('Planificando con %s desde (%.2f, %.2f) hasta (%.2f, %.2f)...\n', ...
    upper(algoritmo), inicio_real(1), inicio_real(2), meta_real(1), meta_real(2));
t_plan = tic;
[ruta_real, ruta_celdas] = planificar_movimiento(map, ...
    inicio_real, meta_real, algoritmo, inflado, n_puntos);
RUTA    = simplificar_ruta(ruta_real, 0.08);   % waypoints cada ~8 cm (menos recorte de curvas)
RUTA_mm = RUTA * 1000;

% Quitar el primer waypoint si coincide con el arranque (evita el
% deadlock de "el primer punto es la posicion actual del robot").
if size(RUTA_mm,1) >= 2
    d0 = hypot(RUTA_mm(1,1)-inicio_real(1)*1000, RUTA_mm(1,2)-inicio_real(2)*1000);
    if d0 < tol_wp
        RUTA_mm(1,:) = [];
    end
end
M = size(RUTA_mm, 1);
fprintf('Ruta lista en %.1f s: %d waypoints a seguir.\n', toc(t_plan), M);

if mostrar_figuras
    try
        figure; imshow(map); hold on;
        plot(ruta_celdas(:,1), ruta_celdas(:,2), 'g-', 'LineWidth', 2);
        plot(ruta_celdas(1,1), ruta_celdas(1,2), 'bo', 'MarkerFaceColor','b');
        plot(ruta_celdas(end,1), ruta_celdas(end,2), 'rp', ...
            'MarkerFaceColor','r', 'MarkerSize', 12);
        title(sprintf('Ruta %s', upper(algoritmo))); axis on; hold off; drawnow;
    catch err
        warning('No se pudo dibujar la figura: %s', err.message);
    end
end

% -----------------------------------------------------------------
% Estado del controlador / pursuit
% -----------------------------------------------------------------
idx = 1;
prev_alpha = 0;  has_prev = false;
paso = 0;

% -----------------------------------------------------------------
% CICLO DE CONTROL (PID exponencial) + EJECUCION DE LA RUTA
% -----------------------------------------------------------------
while wb_robot_step(TIME_STEP) ~= -1
  paso = paso + 1;

  % Pose actual
  pos = wb_gps_get_values(gps);
  mag = wb_compass_get_values(compass);
  posx = pos(1); posy = pos(2);
  bearing = atan2d(mag(2), mag(1)) - 90;
  theta = deg2rad( atan2d(sind(-bearing), cosd(-bearing)) );
  xpos = posx * 1000;  ypos = posy * 1000;   % mm

  % Waypoint objetivo
  xg = RUTA_mm(idx,1);  yg = RUTA_mm(idx,2);
  dx = xg - xpos;  dy = yg - ypos;
  rho = hypot(dx, dy);
  theta_goal = atan2(dy, dx);
  alpha = wrapToPiL(theta_goal - theta);

  % --- Pursuit: avanzar de waypoint o terminar (sobre el CENTRO) ---
  if idx < M
      if rho < tol_wp
          idx = idx + 1;
          continue;   % recalcula con el siguiente waypoint el proximo paso
      end
  else
      if rho < tol_meta
          wb_motor_set_velocity(left_motor, 0.0);
          wb_motor_set_velocity(right_motor, 0.0);
          disp('Meta alcanzada: trayectoria finalizada.');
          break;
      end
  end

  % --- PID con acercamiento exponencial ---
  if ~has_prev
      d_alpha = 0;  has_prev = true;
  else
      d_alpha = (alpha - prev_alpha)/dt;
  end
  prev_alpha = alpha;

  v_mag = v0 * (1 - exp(-alpha_exp * rho^2));   % crece con rho, ~0 cerca
  align = max(cos(alpha), 0);                   % avanza solo si mira al punto
  v = v_mag * align;
  w = kp_w*alpha + kd_w*d_alpha;

  v = sat(v, vmax);
  w = sat(w, wmax);

  % --- Uniciclo -> diferencial (rad/s) -> rpm ---
  dphiR = (v + L2*w) / wheel_radius;
  dphiL = (v - L2*w) / wheel_radius;
  Rrpm = sat(motor_sign*rads2rpm(dphiR), rpm_max);
  Lrpm = sat(motor_sign*rads2rpm(dphiL), rpm_max);

  % --- Anti-atasco: empuja a rpm_min cuando deberia moverse ---
  if rho >= tol_wp
      if abs(Lrpm) > 0 && abs(Lrpm) < rpm_min, Lrpm = rpm_min*sign(Lrpm); end
      if abs(Rrpm) > 0 && abs(Rrpm) < rpm_min, Rrpm = rpm_min*sign(Rrpm); end
  end

  % --- Enviar a motores (el modelo usa signo negativo) ---
  wb_motor_set_velocity(left_motor,  -rpm2rads(Lrpm));
  wb_motor_set_velocity(right_motor, -rpm2rads(Rrpm));

  % Debug ~cada segundo
  if mod(paso, round(1/dt)) == 0
      fprintf('idx=%d/%d  rho=%.0f mm  alpha=%.1f deg  v=%.0f  w=%.2f  L=%.0f R=%.0f rpm\n', ...
          idx, M, rho, rad2deg(alpha), v, w, Lrpm, Rrpm);
  end

  drawnow;
end

wb_motor_set_velocity(left_motor, 0.0);
wb_motor_set_velocity(right_motor, 0.0);

end % function


% =================================================================
%                    LOCAL FUNCTIONS
% =================================================================
function [ruta_real, ruta_celdas, planner] = planificar_movimiento(map, ...
    inicio_real, meta_real, algoritmo, inflado, n_puntos)
    if nargin < 5 || isempty(inflado),  inflado  = 8;   end
    if nargin < 6 || isempty(n_puntos), n_puntos = 250; end
    c_inicio = world2map(inicio_real);
    c_meta   = world2map(meta_real);
    inicio_xy = c_inicio(:);  meta_xy = c_meta(:);
    switch lower(algoritmo)
        case 'dstar'
            planner = Dstar(map, 'inflate', inflado);
            planner.plan(meta_xy);
            ruta_celdas = planner.query(inicio_xy);
        case 'prm'
            planner = PRM(map, 'inflate', inflado);
            planner.plan('npoints', n_puntos);
            ruta_celdas = planner.query(inicio_xy, meta_xy);
        otherwise
            error('Algoritmo no reconocido. Use ''dstar'' o ''prm''.');
    end
    ruta_real = zeros(size(ruta_celdas,1), 2);
    for i = 1:size(ruta_celdas,1)
        ruta_real(i,:) = map2world(ruta_celdas(i,:));
    end
end

function celda = world2map(p_real)
    width = 4*100;  height = 5*100;
    col = round((-p_real(1) + width/200) * 100);
    row = round(( p_real(2) + height/200) * 100);
    celda = [col, row];
end

function p_real = map2world(celda)
    width = 4*100;  height = 5*100;
    X = -(celda(1)/100) + width/200;
    Y =  (celda(2)/100) - height/200;
    p_real = [X, Y];
end

function ruta_s = simplificar_ruta(ruta, paso_min)
    if isempty(ruta), ruta_s = ruta; return; end
    ruta_s = ruta(1,:);  ultimo = ruta(1,:);
    for i = 2:size(ruta,1)-1
        if norm(ruta(i,:) - ultimo) >= paso_min
            ruta_s = [ruta_s; ruta(i,:)]; %#ok<AGROW>
            ultimo = ruta(i,:);
        end
    end
    ruta_s = [ruta_s; ruta(end,:)];
end